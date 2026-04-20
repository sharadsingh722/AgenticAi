"""Smart upload router with agentic document classification and multi-pass extraction."""
import json
import logging
import os
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Resume, Tender
from app.services.pdf_parser import extract_text_from_pdf
from app.services.embedding import (
    embed_texts,
    store_resume_embedding,
    store_tender_role_embedding,
    delete_resume_embedding,
    delete_tender_embeddings,
)
from app.agents.document_agent import document_agent
from app.agents.extraction_agent import extraction_agent
from app.schemas import ResumeParseResult, TenderParseResult, RequiredRole
from app.config import settings
from app.utils.streaming import sse_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/smart")
async def smart_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Smart upload with agentic document classification and multi-pass extraction."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    pdf_bytes = await file.read()
    filename = file.filename

    import hashlib
    pdf_hash = hashlib.md5(pdf_bytes).hexdigest()[:12]
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ").strip()
    pdf_filename = f"{pdf_hash}_{safe_name}"

    async def event_stream():
        # Step 1: Extract text
        yield sse_event("progress", {"step": "extracting", "message": "Extracting text from PDF..."})
        raw_text = extract_text_from_pdf(pdf_bytes)
        if not raw_text.strip():
            yield sse_event("error", {"message": "Could not extract text. The PDF may be scanned."})
            return

        # Step 2: Document Agent - classify + photo detection
        yield sse_event("progress", {"step": "classifying", "message": "AI agent analyzing document type..."})
        doc_result = document_agent.invoke({
            "raw_text": raw_text,
            "file_name": filename,
            "pdf_bytes": pdf_bytes,
            "text_snippet": "",
            "has_images": False,
            "extracted_images": [],
            "classification": "",
            "confidence": 0.0,
            "explanation": "",
            "photo_filename": None,
            "photo_type": None,
            "error": None,
        })

        doc_type = doc_result.get("classification", "other")
        confidence = doc_result.get("confidence", 0)
        explanation = doc_result.get("explanation", "")
        photo_filename = doc_result.get("photo_filename")
        photo_type = doc_result.get("photo_type")

        yield sse_event("progress", {
            "step": "classified",
            "message": f"Detected as {doc_type.upper()} ({confidence:.0%} confidence)",
            "type": doc_type,
            "explanation": explanation,
            "photo_type": photo_type,
        })

        if doc_type not in ("resume", "tender"):
            yield sse_event("complete", {
                "type": doc_type,
                "message": f"This document appears to be a {doc_type}. {explanation}",
                "suggestion": "Only resumes and tenders can be processed for matching.",
            })
            return

        existing_resume = None
        existing_tender = None
        yield sse_event("progress", {"step": "dedup_check", "message": "Checking for existing file..."})
        if doc_type == "resume":
            existing_resume = db.query(Resume).filter(Resume.file_name == filename).first()
            if existing_resume:
                yield sse_event("progress", {
                    "step": "dedup_check",
                    "message": f"Existing resume found for '{filename}', reparsing and updating it...",
                })
        else:
            existing_tender = db.query(Tender).filter(Tender.file_name == filename).first()
            if existing_tender:
                yield sse_event("progress", {
                    "step": "dedup_check",
                    "message": f"Existing tender found for '{filename}', reparsing and updating it...",
                })

        # Step 3: Extraction Agent - multi-pass
        yield sse_event("progress", {"step": "extracting_pass_1", "message": "Pass 1: Analyzing document structure..."})
        ext_state = {
            "raw_text": raw_text,
            "doc_type": doc_type,
            "document_structure": "",
            "sections": [],
            "extracted_data": {},
            "verification_issues": [],
            "is_verified": False,
            "final_data": {},
            "pass_count": 0,
            "error": None,
        }

        # Run extraction agent step by step for progress streaming
        # We invoke the full graph and stream progress based on pass_count
        yield sse_event("progress", {"step": "extracting_pass_2", "message": "Pass 2: Deep extraction with AI reasoning..."})

        ext_result = extraction_agent.invoke(ext_state)
        final_data = ext_result.get("final_data", ext_result.get("extracted_data", {}))

        # Retry once if extraction returned empty/Unknown name
        if doc_type == "resume" and final_data.get("name", "Unknown") in ("Unknown", "", None):
            yield sse_event("progress", {"step": "retrying", "message": "Extraction incomplete, retrying..."})
            ext_result = extraction_agent.invoke(ext_state)
            final_data = ext_result.get("final_data", ext_result.get("extracted_data", {}))

        if ext_result.get("verification_issues"):
            yield sse_event("progress", {"step": "verifying", "message": f"Verified with {len(ext_result['verification_issues'])} corrections applied"})
        else:
            yield sse_event("progress", {"step": "verifying", "message": "Verified - no issues found"})

        # Step 4: Store in DB + embed
        yield sse_event("progress", {"step": "embedding", "message": "Generating AI embeddings..."})

        if doc_type == "resume":
            # Validation Layer: Ensure lists are lists and numerics are safe
            final_data["skills"] = final_data.get("skills") if isinstance(final_data.get("skills"), list) else []
            final_data["domain_expertise"] = final_data.get("domain_expertise") if isinstance(final_data.get("domain_expertise"), list) else []
            final_data["education"] = final_data.get("education") if isinstance(final_data.get("education"), list) else []
            final_data["certifications"] = final_data.get("certifications") if isinstance(final_data.get("certifications"), list) else []
            try:
                final_data["total_years_experience"] = float(final_data.get("total_years_experience", 0.0))
            except (ValueError, TypeError):
                final_data["total_years_experience"] = 0.0
                
            for exp in final_data.get("experience", []):
                if not isinstance(exp, dict): continue
                exp["components"] = exp.get("components") if isinstance(exp.get("components"), list) else []
                try: exp["project_value_cr"] = float(exp.get("project_value_cr", 0.0) or 0.0)
                except: exp["project_value_cr"] = 0.0
                try: exp["length_km"] = float(exp.get("length_km", 0.0) or 0.0)
                except: exp["length_km"] = 0.0

            try:
                parsed = ResumeParseResult(**final_data)
            except Exception as e:
                logger.error(f"Validation failed for resume: {e}")
                parsed = ResumeParseResult()

            parse_status = "failed" if parsed.name in ("Unknown", "Parse Failed") else "success"

            # Save original PDF backup for Resume
            os.makedirs(os.path.join(settings.upload_dir, "resumes"), exist_ok=True)
            pdf_path = os.path.join(settings.upload_dir, "resumes", pdf_filename)
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)

            if existing_resume:
                db_resume = existing_resume
                delete_resume_embedding(db_resume.id)
            else:
                db_resume = Resume(file_name=filename, raw_text=raw_text, name=parsed.name)
                db.add(db_resume)

            db_resume.name = parsed.name
            db_resume.email = parsed.email
            db_resume.phone = parsed.phone
            db_resume.skills = json.dumps(parsed.skills)
            db_resume.experience = json.dumps([exp.model_dump() for exp in parsed.experience])
            db_resume.education = json.dumps(parsed.education)
            db_resume.certifications = json.dumps(parsed.certifications)
            db_resume.total_years_experience = parsed.total_years_experience
            db_resume.domain_expertise = json.dumps(parsed.domain_expertise)
            db_resume.raw_text = raw_text
            db_resume.file_name = filename
            db_resume.photo_filename = photo_filename
            db_resume.pdf_filename = pdf_filename
            db_resume.parsed_data = json.dumps(parsed.model_dump())
            db_resume.field_resolution = json.dumps(parsed.field_resolution.model_dump())
            db_resume.standardized_skills = json.dumps(parsed.standardized_skills)
            db_resume.standardized_education = json.dumps(parsed.standardized_education)
            db_resume.parse_status = parse_status
            db.commit()
            db.refresh(db_resume)

            if parse_status == "success":
                try:
                    embeddings = await embed_texts([raw_text])
                    store_resume_embedding(db_resume.id, embeddings[0], {
                        "resume_id": db_resume.id,
                        "name": parsed.name,
                        "skills": ", ".join(parsed.skills[:20]),
                        "total_years_experience": parsed.total_years_experience,
                        "domain_expertise": ", ".join(parsed.domain_expertise[:10]),
                        "summary": f"{parsed.name} - {parsed.total_years_experience} years",
                        "has_railway": parsed.derived_profile.has_railway_experience,
                        "has_epc": parsed.derived_profile.has_epc_experience,
                    })
                except Exception as e:
                    logger.error(f"Embedding failed: {e}")

            photo_url = f"/api/resumes/photo/{photo_filename}" if photo_filename else None
            yield sse_event("complete", {
                "type": "resume",
                "id": db_resume.id,
                "name": parsed.name,
                "skills_count": len(parsed.skills),
                "experience_years": parsed.total_years_experience,
                "photo_url": photo_url,
                "photo_type": photo_type,
                "parse_status": parse_status,
                "passes": ext_result.get("pass_count", 3),
                "issues_fixed": len(ext_result.get("verification_issues", [])),
            })

        else:  # tender
            # Validation Layer: Ensure lists are lists and numerics are safe
            final_data["key_technologies"] = final_data.get("key_technologies") if isinstance(final_data.get("key_technologies"), list) else []
            final_data["eligibility_criteria"] = final_data.get("eligibility_criteria") if isinstance(final_data.get("eligibility_criteria"), list) else []
            for role in final_data.get("required_roles", []):
                if not isinstance(role, dict): continue
                role["required_skills"] = role.get("required_skills") if isinstance(role.get("required_skills"), list) else []
                role["required_domain"] = role.get("required_domain") if isinstance(role.get("required_domain"), list) else []
                role["preferred_components"] = role.get("preferred_components") if isinstance(role.get("preferred_components"), list) else []
                role["required_certifications"] = role.get("required_certifications") if isinstance(role.get("required_certifications"), list) else []
                try: role["min_experience"] = float(role.get("min_experience", 0.0) or 0.0)
                except: role["min_experience"] = 0.0
                try: role["min_project_value_cr"] = float(role.get("min_project_value_cr", 0.0) or 0.0)
                except: role["min_project_value_cr"] = 0.0

            try:
                parsed = TenderParseResult(**final_data)
            except Exception as e:
                logger.error(f"Validation failed for tender: {e}")
                parsed = TenderParseResult()

            parse_status = "failed" if parsed.project_name in ("Unknown Project", "Parse Failed") else "success"

            # Save original PDF backup for Tender
            os.makedirs(os.path.join(settings.upload_dir, "tenders"), exist_ok=True)
            pdf_path = os.path.join(settings.upload_dir, "tenders", pdf_filename)
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)

            if existing_tender:
                db_tender = existing_tender
                delete_tender_embeddings(db_tender.id)
            else:
                db_tender = Tender(file_name=filename, raw_text=raw_text, project_name=parsed.project_name)
                db.add(db_tender)

            db_tender.project_name = parsed.project_name
            db_tender.client = parsed.client
            db_tender.document_reference = parsed.document_reference
            db_tender.document_date = parsed.document_date
            db_tender.required_roles = json.dumps([role.model_dump() for role in parsed.required_roles])
            db_tender.eligibility_criteria = json.dumps(parsed.eligibility_criteria)
            db_tender.project_duration = parsed.project_duration
            db_tender.key_technologies = json.dumps(parsed.key_technologies)
            db_tender.raw_text = raw_text
            db_tender.file_name = filename
            db_tender.pdf_filename = pdf_filename
            db_tender.parsed_data = json.dumps(parsed.model_dump())
            db_tender.parse_status = parse_status
            db.commit()
            db.refresh(db_tender)

            if parse_status == "success" and parsed.required_roles:
                try:
                    for i, role in enumerate(parsed.required_roles):
                        role_text = f"{role.role_title}. Skills: {', '.join(role.required_skills)}. "
                        role_text += f"Experience: {role.min_experience} years. "
                        role_text += f"Domain: {', '.join(role.required_domain)}. "
                        if role.preferred_components:
                            role_text += f"Components: {', '.join(role.preferred_components)}. "
                        if role.min_project_value_cr > 0:
                            role_text += f"Project scale > {role.min_project_value_cr} Cr."
                        
                        embeddings = await embed_texts([role_text])
                        store_tender_role_embedding(db_tender.id, i, embeddings[0], {
                            "tender_id": db_tender.id,
                            "role_title": role.role_title,
                        })
                except Exception as e:
                    logger.error(f"Role embedding failed: {e}")

            yield sse_event("complete", {
                "type": "tender",
                "id": db_tender.id,
                "project_name": parsed.project_name,
                "client": parsed.client,
                "document_reference": parsed.document_reference,
                "roles_count": len(parsed.required_roles),
                "parse_status": parse_status,
                "passes": ext_result.get("pass_count", 3),
                "issues_fixed": len(ext_result.get("verification_issues", [])),
            })

    return StreamingResponse(event_stream(), media_type="text/event-stream")

import json
import logging
import os
import hashlib
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Resume
from app.schemas import ResumeResponse, ResumeDetailResponse, ExperienceItem
from app.services.pdf_parser import extract_text_from_pdf, extract_photo_from_pdf
from app.services.llm_extractor import extract_resume_data
from app.services.embedding import embed_texts, store_resume_embedding, delete_resume_embedding
from app.services.ingestion import process_rag_indexing
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/resumes", tags=["resumes"])


def _resume_to_response(resume: Resume) -> ResumeResponse:
    photo_url = f"/api/resumes/photo/{resume.photo_filename}" if resume.photo_filename else None
    return ResumeResponse(
        id=resume.id,
        name=resume.name,
        email=resume.email,
        phone=resume.phone,
        skills=json.loads(resume.skills) if resume.skills else [],
        total_years_experience=resume.total_years_experience,
        domain_expertise=json.loads(resume.domain_expertise) if resume.domain_expertise else [],
        file_name=resume.file_name,
        photo_url=photo_url,
        pdf_filename=resume.pdf_filename,
        parse_status=resume.parse_status,
        created_at=resume.created_at,
    )


def _resume_to_detail(resume: Resume) -> ResumeDetailResponse:
    experience_data = json.loads(resume.experience) if resume.experience else []
    experience = [ExperienceItem(**exp) if isinstance(exp, dict) else exp for exp in experience_data]

    return ResumeDetailResponse(
        id=resume.id,
        name=resume.name,
        email=resume.email,
        phone=resume.phone,
        skills=json.loads(resume.skills) if resume.skills else [],
        total_years_experience=resume.total_years_experience,
        domain_expertise=json.loads(resume.domain_expertise) if resume.domain_expertise else [],
        file_name=resume.file_name,
        photo_url=f"/api/resumes/photo/{resume.photo_filename}" if resume.photo_filename else None,
        pdf_filename=resume.pdf_filename,
        parse_status=resume.parse_status,
        created_at=resume.created_at,
        experience=experience,
        education=json.loads(resume.education) if resume.education else [],
        certifications=json.loads(resume.certifications) if resume.certifications else [],
        raw_text=resume.raw_text or "",
    )


@router.post("/upload", response_model=ResumeResponse)
async def upload_resume(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload and parse a resume PDF."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Read PDF bytes
    pdf_bytes = await file.read()

    # Save original PDF backup
    os.makedirs(os.path.join(settings.upload_dir, "resumes"), exist_ok=True)
    pdf_hash = hashlib.md5(pdf_bytes).hexdigest()[:12]
    # We use a unique filename based on hash and original name to avoid collisions
    safe_name = "".join(c for c in file.filename if c.isalnum() or c in "._- ").strip()
    pdf_filename = f"{pdf_hash}_{safe_name}"
    pdf_path = os.path.join(settings.upload_dir, "resumes", pdf_filename)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    # Extract text
    raw_text = extract_text_from_pdf(pdf_bytes)
    if not raw_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Could not extract text from PDF. It may be a scanned document.",
        )

    # Extract structured data via LLM
    parsed = await extract_resume_data(raw_text)
    parse_status = "failed" if parsed.name == "Parse Failed" else "success"

    # Extract photo
    photo_filename = extract_photo_from_pdf(pdf_bytes, settings.upload_dir)

    # Create database record
    db_resume = Resume(
        name=parsed.name,
        email=parsed.email,
        phone=parsed.phone,
        skills=json.dumps(parsed.skills),
        experience=json.dumps([exp.model_dump() for exp in parsed.experience]),
        education=json.dumps(parsed.education),
        certifications=json.dumps(parsed.certifications),
        total_years_experience=parsed.total_years_experience,
        domain_expertise=json.dumps(parsed.domain_expertise),
        raw_text=raw_text,
        file_name=file.filename,
        photo_filename=photo_filename,
        pdf_filename=pdf_filename,
        parsed_data=json.dumps(parsed.model_dump()),
        field_resolution=json.dumps(parsed.field_resolution.model_dump()),
        standardized_skills=json.dumps(parsed.standardized_skills),
        standardized_education=json.dumps(parsed.standardized_education),
        parse_status=parse_status,
    )
    db.add(db_resume)
    db.commit()
    db.refresh(db_resume)

    # Generate and store embedding
    if parse_status == "success":
        try:
            embeddings = await embed_texts([raw_text])
            metadata = {
                "resume_id": db_resume.id,
                "name": parsed.name,
                "skills": ", ".join(parsed.skills[:20]),  # ChromaDB metadata has size limits
                "total_years_experience": parsed.total_years_experience,
                "domain_expertise": ", ".join(parsed.domain_expertise[:10]),
                "summary": f"{parsed.name} - {parsed.total_years_experience} years - {', '.join(parsed.skills[:5])}",
            }
            store_resume_embedding(db_resume.id, embeddings[0], metadata)
        except Exception as e:
            logger.error(f"Failed to store embedding for resume {db_resume.id}: {e}")

    # Index for surgical RAG in background
    background_tasks.add_task(process_rag_indexing, db_resume.id, "resume", raw_text)

    return _resume_to_response(db_resume)


@router.post("/upload-batch")
async def upload_resumes_batch(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Upload multiple resume PDFs at once."""
    results = []
    errors = []

    for file in files:
        try:
            if not file.filename.lower().endswith(".pdf"):
                errors.append({"file": file.filename, "error": "Not a PDF file"})
                continue

            pdf_bytes = await file.read()

            # Save original PDF backup
            os.makedirs(os.path.join(settings.upload_dir, "resumes"), exist_ok=True)
            pdf_hash = hashlib.md5(pdf_bytes).hexdigest()[:12]
            safe_name = "".join(c for c in file.filename if c.isalnum() or c in "._- ").strip()
            pdf_filename = f"{pdf_hash}_{safe_name}"
            pdf_path = os.path.join(settings.upload_dir, "resumes", pdf_filename)
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)

            raw_text = extract_text_from_pdf(pdf_bytes)

            if not raw_text.strip():
                errors.append({"file": file.filename, "error": "Could not extract text"})
                continue

            parsed = await extract_resume_data(raw_text)
            parse_status = "failed" if parsed.name == "Parse Failed" else "success"

            # Extract photo
            photo_filename = extract_photo_from_pdf(pdf_bytes, settings.upload_dir)

            db_resume = Resume(
                name=parsed.name,
                email=parsed.email,
                phone=parsed.phone,
                skills=json.dumps(parsed.skills),
                experience=json.dumps([exp.model_dump() for exp in parsed.experience]),
                education=json.dumps(parsed.education),
                certifications=json.dumps(parsed.certifications),
                total_years_experience=parsed.total_years_experience,
                domain_expertise=json.dumps(parsed.domain_expertise),
                raw_text=raw_text,
                file_name=file.filename,
                photo_filename=photo_filename,
                pdf_filename=pdf_filename,
                parsed_data=json.dumps(parsed.model_dump()),
                field_resolution=json.dumps(parsed.field_resolution.model_dump()),
                standardized_skills=json.dumps(parsed.standardized_skills),
                standardized_education=json.dumps(parsed.standardized_education),
                parse_status=parse_status,
            )
            db.add(db_resume)
            db.commit()
            db.refresh(db_resume)

            if parse_status == "success":
                try:
                    embeddings = await embed_texts([raw_text])
                    metadata = {
                        "resume_id": db_resume.id,
                        "name": parsed.name,
                        "skills": ", ".join(parsed.skills[:20]),
                        "total_years_experience": parsed.total_years_experience,
                        "domain_expertise": ", ".join(parsed.domain_expertise[:10]),
                        "summary": f"{parsed.name} - {parsed.total_years_experience} years",
                    }
                    store_resume_embedding(db_resume.id, embeddings[0], metadata)
                except Exception as e:
                    logger.error(f"Embedding failed for {file.filename}: {e}")

            # Index for surgical RAG in background
            background_tasks.add_task(process_rag_indexing, db_resume.id, "resume", raw_text)

            results.append(_resume_to_response(db_resume))

        except Exception as e:
            errors.append({"file": file.filename, "error": str(e)})

    return {"uploaded": len(results), "errors": errors, "resumes": results}


@router.get("", response_model=list[ResumeResponse])
async def list_resumes(db: Session = Depends(get_db)):
    """List all resumes."""
    resumes = db.query(Resume).order_by(Resume.created_at.desc()).all()
    return [_resume_to_response(r) for r in resumes]


@router.get("/{resume_id}", response_model=ResumeDetailResponse)
async def get_resume(resume_id: int, db: Session = Depends(get_db)):
    """Get detailed resume information."""
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return _resume_to_detail(resume)


@router.delete("/{resume_id}")
async def delete_resume(resume_id: int, db: Session = Depends(get_db)):
    """Delete a resume and its embedding."""
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    delete_resume_embedding(resume_id)
    db.delete(resume)
    db.commit()
    return {"message": f"Resume {resume_id} deleted"}


@router.get("/photo/{filename}")
async def get_photo(filename: str):
    """Serve an extracted resume photo."""
    filepath = os.path.join(settings.upload_dir, "photos", filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(filepath)


@router.get("/{resume_id}/download")
async def download_resume_pdf(resume_id: int, db: Session = Depends(get_db)):
    """Download the original backed-up PDF resume."""
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume or not resume.pdf_filename:
        raise HTTPException(status_code=404, detail="Original PDF not found")
    
    filepath = os.path.join(settings.upload_dir, "resumes", resume.pdf_filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="PDF file not found on disk")
        
    return FileResponse(
        filepath, 
        media_type='application/pdf',
        filename=resume.file_name
    )

import json
import logging
import os
import hashlib
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Tender
from app.schemas import TenderResponse, TenderDetailResponse, RequiredRole
from app.services.pdf_parser import extract_text_from_pdf
from app.services.llm_extractor import extract_tender_data
from app.services.embedding import embed_texts, store_tender_role_embedding, delete_tender_embeddings
from app.services.ingestion import process_rag_indexing
from app.config import settings
router = APIRouter(prefix="/tenders", tags=["tenders"])


def _count_meaningful_roles(roles: list) -> int:
    """Count roles that have actual requirements (skills or min_experience > 0)."""
    count = 0
    for r in roles:
        has_skills = len(r.get("required_skills", [])) > 0
        has_exp = r.get("min_experience", 0) > 0
        has_certs = len(r.get("required_certifications", [])) > 0
        has_domain = len(r.get("required_domain", [])) > 0
        if has_skills or has_exp or has_certs or has_domain:
            count += 1
    return count


def _tender_to_response(tender: Tender) -> TenderResponse:
    roles = json.loads(tender.required_roles) if tender.required_roles else []
    technologies = json.loads(tender.key_technologies) if tender.key_technologies else []

    return TenderResponse(
        id=tender.id,
        project_name=tender.project_name,
        client=tender.client,
        document_reference=tender.document_reference,
        document_date=tender.document_date,
        roles_count=_count_meaningful_roles(roles),
        key_technologies=technologies,
        file_name=tender.file_name,
        pdf_filename=tender.pdf_filename,
        parse_status=tender.parse_status,
        created_at=tender.created_at,
    )


def _tender_to_detail(tender: Tender) -> TenderDetailResponse:
    roles_data = json.loads(tender.required_roles) if tender.required_roles else []
    roles = [RequiredRole(**r) if isinstance(r, dict) else r for r in roles_data]

    return TenderDetailResponse(
        id=tender.id,
        project_name=tender.project_name,
        client=tender.client,
        document_reference=tender.document_reference,
        document_date=tender.document_date,
        required_roles=roles,
        eligibility_criteria=json.loads(tender.eligibility_criteria) if tender.eligibility_criteria else [],
        project_duration=tender.project_duration,
        key_technologies=json.loads(tender.key_technologies) if tender.key_technologies else [],
        file_name=tender.file_name,
        pdf_filename=tender.pdf_filename,
        parse_status=tender.parse_status,
        raw_text=tender.raw_text or "",
        created_at=tender.created_at,
    )


@router.post("/upload", response_model=TenderResponse)
async def upload_tender(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload and parse a tender/RFP PDF."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    pdf_bytes = await file.read()

    # Save original PDF backup
    os.makedirs(os.path.join(settings.upload_dir, "tenders"), exist_ok=True)
    pdf_hash = hashlib.md5(pdf_bytes).hexdigest()[:12]
    safe_name = "".join(c for c in file.filename if c.isalnum() or c in "._- ").strip()
    pdf_filename = f"{pdf_hash}_{safe_name}"
    pdf_path = os.path.join(settings.upload_dir, "tenders", pdf_filename)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    raw_text = extract_text_from_pdf(pdf_bytes)

    if not raw_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Could not extract text from PDF. It may be a scanned document.",
        )

    # Extract structured data via LLM
    parsed = await extract_tender_data(raw_text)
    parse_status = "failed" if parsed.project_name == "Parse Failed" else "success"

    db_tender = Tender(
        project_name=parsed.project_name,
        client=parsed.client,
        document_reference=parsed.document_reference,
        document_date=parsed.document_date,
        required_roles=json.dumps([role.model_dump() for role in parsed.required_roles]),
        eligibility_criteria=json.dumps(parsed.eligibility_criteria),
        project_duration=parsed.project_duration,
        key_technologies=json.dumps(parsed.key_technologies),
        raw_text=raw_text,
        file_name=file.filename,
        pdf_filename=pdf_filename,
        parsed_data=json.dumps(parsed.model_dump()),
        parse_status=parse_status,
    )
    db.add(db_tender)
    db.commit()
    db.refresh(db_tender)

    # Generate embeddings for each role
    if parse_status == "success" and parsed.required_roles:
        try:
            for i, role in enumerate(parsed.required_roles):
                role_text = f"{role.role_title}. "
                role_text += f"Skills: {', '.join(role.required_skills)}. "
                role_text += f"Experience: {role.min_experience} years. "
                role_text += f"Domain: {', '.join(role.required_domain)}. "
                role_text += f"Certifications: {', '.join(role.required_certifications)}."

                embeddings = await embed_texts([role_text])
                metadata = {
                    "tender_id": db_tender.id,
                    "role_title": role.role_title,
                    "role_description": role_text,
                }
                store_tender_role_embedding(db_tender.id, i, embeddings[0], metadata)
        except Exception as e:
            logger.error(f"Failed to store role embeddings for tender {db_tender.id}: {e}")

    # Index for surgical RAG in background
    background_tasks.add_task(process_rag_indexing, db_tender.id, "tender", raw_text)

    return _tender_to_response(db_tender)


@router.get("", response_model=list[TenderResponse])
async def list_tenders(db: Session = Depends(get_db)):
    """List all tenders."""
    tenders = db.query(Tender).order_by(Tender.created_at.desc()).all()
    return [_tender_to_response(t) for t in tenders]


@router.get("/{tender_id}", response_model=TenderDetailResponse)
async def get_tender(tender_id: int, db: Session = Depends(get_db)):
    """Get detailed tender information."""
    tender = db.query(Tender).filter(Tender.id == tender_id).first()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
    return _tender_to_detail(tender)


@router.delete("/{tender_id}")
async def delete_tender(tender_id: int, db: Session = Depends(get_db)):
    """Delete a tender and its embeddings."""
    tender = db.query(Tender).filter(Tender.id == tender_id).first()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    delete_tender_embeddings(tender_id)
    db.delete(tender)
    db.commit()
    return {"message": f"Tender {tender_id} deleted"}


@router.get("/{tender_id}/download")
async def download_tender_pdf(tender_id: int, db: Session = Depends(get_db)):
    """Download the original tender PDF document."""
    tender = db.query(Tender).filter(Tender.id == tender_id).first()
    if not tender or not tender.pdf_filename:
        raise HTTPException(status_code=404, detail="PDF backup not found for this tender")

    import os
    file_path = os.path.join("data", "uploads", "tenders", tender.pdf_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on server")

    return FileResponse(
        path=file_path,
        filename=tender.file_name,
        media_type="application/pdf"
    )

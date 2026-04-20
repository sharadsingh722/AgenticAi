import logging
import os
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Resume, Tender, ResumeChunk, TenderChunk
from app.services.markdown_converter import MarkdownConverter
from app.services.chunk_manager import ChunkManager
from app.services.embedding import store_resume_chunks_vdb, store_tender_chunks_vdb
from app.services.logical_merger import DocumentType
from app.config import settings

logger = logging.getLogger(__name__)

async def process_rag_indexing(doc_id: int, doc_type: str, cleaned_text: str = ""):
    """Background task to chunk and index a document for surgical RAG."""
    db = SessionLocal()
    try:
        # Update status to indexing
        if doc_type == "resume":
            db.query(Resume).filter(Resume.id == doc_id).update({"rag_status": "indexing"})
        else:
            db.query(Tender).filter(Tender.id == doc_id).update({"rag_status": "indexing"})
        db.commit()

        if doc_type == "resume":
            resume = db.query(Resume).filter(Resume.id == doc_id).first()
            if not resume: return
            
            # Fetch actual file path
            upload_dir = os.path.join(settings.upload_dir, "resumes")
            file_path = os.path.join(upload_dir, resume.file_name)
            
            # Extract MD with High-Fidelity Pipeline
            if os.path.exists(file_path):
                logger.info(f"Using High-Fidelity Converter for Resume {doc_id}")
                healed_md = MarkdownConverter.convert(file_path, doc_type=DocumentType.RESUME)
                
                # Save MD to DB
                db.query(Resume).filter(Resume.id == doc_id).update({"markdown_text": healed_md})
                db.commit()
                
                chunks = ChunkManager.create_chunks(healed_md, is_resume=True, file_name=resume.file_name)
            else:
                # Fallback to current cleaned_text if file missing
                chunks = ChunkManager.create_chunks(cleaned_text or resume.raw_text, is_resume=True, file_name=resume.file_name)
                
            if not chunks:
                db.query(Resume).filter(Resume.id == doc_id).update({"rag_status": "failed"})
                db.commit()
                return

            db_chunks = [ResumeChunk(resume_id=doc_id, chunk_index=i, content=c) for i, c in enumerate(chunks)]
            db.add_all(db_chunks)
            await store_resume_chunks_vdb(doc_id, chunks)
            
            db.query(Resume).filter(Resume.id == doc_id).update({"rag_status": "completed"})
            db.commit()
            logger.info(f"RAG Indexing complete for Resume {doc_id} using High-Fi MD")

        elif doc_type == "tender":
            tender = db.query(Tender).filter(Tender.id == doc_id).first()
            if not tender: return
            
            upload_dir = os.path.join(settings.upload_dir, "tenders")
            file_path = os.path.join(upload_dir, tender.file_name)
            
            if os.path.exists(file_path):
                logger.info(f"Using High-Fidelity Converter for Tender {doc_id}")
                healed_md = MarkdownConverter.convert(file_path, doc_type=DocumentType.RFP)
                
                # Save MD to DB
                db.query(Tender).filter(Tender.id == doc_id).update({"markdown_text": healed_md})
                db.commit()
                
                chunks = ChunkManager.create_chunks(healed_md, is_resume=False, file_name=tender.file_name)
            else:
                chunks = ChunkManager.create_chunks(cleaned_text or tender.raw_text, is_resume=False, file_name=tender.file_name)

            if not chunks:
                db.query(Tender).filter(Tender.id == doc_id).update({"rag_status": "failed"})
                db.commit()
                return

            db_chunks = [TenderChunk(tender_id=doc_id, chunk_index=i, content=c) for i, c in enumerate(chunks)]
            db.add_all(db_chunks)
            await store_tender_chunks_vdb(doc_id, chunks)
            
            db.query(Tender).filter(Tender.id == doc_id).update({"rag_status": "completed"})
            db.commit()
            logger.info(f"RAG Indexing complete for Tender {doc_id} using High-Fi MD")

    except Exception as e:
        logger.error(f"RAG Indexing failed for {doc_type} {doc_id}: {e}", exc_info=True)
        try:
            target_model = Resume if doc_type == "resume" else Tender
            db.query(target_model).filter(target_model.id == doc_id).update({"rag_status": "failed"})
            db.commit()
        except: pass
    finally:
        db.close()

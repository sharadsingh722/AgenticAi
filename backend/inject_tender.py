import sys
import os
import asyncio
import json
import hashlib

# Add backend to path
sys.path.append(os.path.abspath('d:/agentic project/resume_tender_match_agent/backend'))

from app.database import SessionLocal
from app.models import Tender
from app.services.pdf_parser import extract_text_from_pdf
from app.services.llm_extractor import extract_tender_data
from app.services.embedding import embed_texts, store_tender_role_embedding
from app.services.ingestion import process_rag_indexing
from app.config import settings

async def inject_tender():
    file_path = r"d:\agentic project\resume_tender_match_agent\backend\data\uploads\software_tender_sample.pdf"
    filename = "software_tender_sample.pdf"

    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    with open(file_path, "rb") as f:
        pdf_bytes = f.read()

    # 1. Extract Text
    print("Extracting text...")
    raw_text = extract_text_from_pdf(pdf_bytes)

    # 2. Extract structured data via LLM
    print("Extracting structured data via LLM...")
    parsed = await extract_tender_data(raw_text)
    
    # 3. Save to DB
    print("Saving to database...")
    db = SessionLocal()
    try:
        pdf_hash = hashlib.md5(pdf_bytes).hexdigest()[:12]
        pdf_filename = f"{pdf_hash}_{filename}"
        
        # Ensure target dir exists
        os.makedirs(os.path.join(settings.upload_dir, "tenders"), exist_ok=True)
        target_path = os.path.join(settings.upload_dir, "tenders", pdf_filename)
        with open(target_path, "wb") as f:
            f.write(pdf_bytes)

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
            file_name=filename,
            pdf_filename=pdf_filename,
            parsed_data=json.dumps(parsed.model_dump()),
            parse_status="success",
        )
        db.add(db_tender)
        db.commit()
        db.refresh(db_tender)

        print(f"Tender ID {db_tender.id} created: {db_tender.project_name}")

        # 4. Generate embeddings
        print("Generating embeddings for roles...")
        for i, role in enumerate(parsed.required_roles):
            role_text = f"{role.role_title}. Skills: {', '.join(role.required_skills)}. Experience: {role.min_experience} yrs."
            embeddings = await embed_texts([role_text])
            metadata = {"tender_id": db_tender.id, "role_title": role.role_title}
            store_tender_role_embedding(db_tender.id, i, embeddings[0], metadata)

        # 5. Index for RAG
        print("Indexing for RAG...")
        process_rag_indexing(db_tender.id, "tender", raw_text)
        
        print("\nAll done! You can now view this tender in the Matching Dashboard.")

    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(inject_tender())

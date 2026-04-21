import asyncio
import os
import json
import logging
import sys

# Add the project root to sys.path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Tender
from app.services.embedding import embed_texts, store_tender_embedding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def backfill_tenders():
    """Generate high-level embeddings for existing tenders."""
    db = SessionLocal()
    try:
        tenders = db.query(Tender).all()
        logger.info(f"Found {len(tenders)} tenders to backfill.")
        
        for tender in tenders:
            logger.info(f"Processing Tender ID {tender.id}: {tender.project_name}")
            
            # Create a summary for embedding
            summary = f"{tender.project_name}. {tender.client or ''}. {tender.raw_text[:500]}"
            
            try:
                embeddings = await embed_texts([summary])
                metadata = {
                    "tender_id": tender.id,
                    "project_name": tender.project_name,
                    "client": tender.client or "N/A"
                }
                store_tender_embedding(tender.id, embeddings[0], metadata)
                logger.info(f"Successfully indexed Tender ID {tender.id}")
            except Exception as e:
                logger.error(f"Error indexing Tender ID {tender.id}: {e}")
                
        logger.info("Backfill complete.")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(backfill_tenders())

import os
import sys
import logging
import hashlib
from sqlalchemy.orm import Session

# Add backend to path for imports
sys.path.append(os.getcwd())

from app.database import SessionLocal, engine
from app.models.resume import Resume
from app.services.pdf_parser import extract_photo_from_pdf
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reprocess_resumes")

def reprocess():
    db = SessionLocal()
    try:
        # Find resumes with missing photos
        resumes_to_fix = db.query(Resume).filter(Resume.photo_filename == None).all()
        logger.info(f"Checking {len(resumes_to_fix)} resumes for photo repair...")

        resumes_dir = os.path.join(settings.upload_dir, "resumes")
        if not os.path.exists(resumes_dir):
            logger.error(f"Resumes directory not found: {resumes_dir}")
            return

        available_files = os.listdir(resumes_dir)
        
        repaired_count = 0
        for resume in resumes_to_fix:
            original_name = resume.file_name
            # Find a matching file in the backup dir
            # Filenames are like {hash}_{safe_name}
            safe_name = "".join(c for c in original_name if c.isalnum() or c in "._- ").strip()
            
            matching_file = next((f for f in available_files if safe_name in f), None)
            
            if matching_file:
                logger.info(f"Found backup for {original_name}: {matching_file}")
                file_path = os.path.join(resumes_dir, matching_file)
                
                with open(file_path, "rb") as f:
                    pdf_bytes = f.read()
                
                # Re-run extraction (now with Super Scan logic)
                photo_filename = extract_photo_from_pdf(pdf_bytes, settings.upload_dir)
                
                if photo_filename:
                    logger.info(f"SUCCESS: Extracted photo for {resume.name}: {photo_filename}")
                    resume.photo_filename = photo_filename
                    repaired_count += 1
                else:
                    logger.info(f"STILL NONE: No photo found in {matching_file} after Super Scan.")
            else:
                logger.info(f"MISSING BACKUP: No saved PDF found for {original_name}. (Probably uploaded before backup system was active)")

        db.commit()
        logger.info(f"Done! Repaired {repaired_count} resumes.")

    finally:
        db.close()

if __name__ == "__main__":
    reprocess()


import os
import sys
import asyncio
import json

# Add parent directory to path
sys.path.insert(0, os.getcwd())

from app.database import SessionLocal
from app.models import Resume
from app.services.llm_extractor import extract_resume_data

async def reparse_specific(resume_id):
    db = SessionLocal()
    try:
        r = db.query(Resume).filter(Resume.id == resume_id).first()
        if not r:
            print(f"Resume ID {resume_id} not found.")
            return
            
        print(f"Reparsing {r.name} (ID: {r.id})...")
        parsed_result = await extract_resume_data(r.raw_text)
        
        print(f"Results for {r.name}:")
        print(f"  Name: {parsed_result.name}")
        print(f"  Exp Years: {parsed_result.total_years_experience}")
        print(f"  Edu: {parsed_result.standardized_education}")
        print(f"  Domains: {parsed_result.domain_expertise}")
        
        r.total_years_experience = parsed_result.total_years_experience
        r.standardized_education = json.dumps(parsed_result.standardized_education)
        r.domain_expertise = json.dumps(parsed_result.domain_expertise)
        r.parsed_data = parsed_result.model_dump_json()
        
        db.commit()
        print("Updated in database.")
    finally:
        db.close()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Reparse candidates who should be in IT domain
    # Harshit(15), Tania(14), Mukesh(12), Rishabh(11)
    for rid in [15, 14, 12, 11]:
        asyncio.run(reparse_specific(rid))

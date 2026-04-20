# Add current directory to sys.path first to avoid conflicts with global 'app' modules
import os
import sys
import asyncio
import json
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.database import SessionLocal
from app.models import Resume, CommonSkill, CommonEducation
from app.services.llm_extractor import extract_resume_data

async def reparse_all():
    db = SessionLocal()
    try:
        resumes = db.query(Resume).all()
        print(f"Found {len(resumes)} resumes to re-parse.")
        
        for r in resumes:
            print(f"Processing Resume ID {r.id}: {r.name}...")
            
            # Use the existing extract_resume_data service which now uses the improved agent
            parsed_result = await extract_resume_data(r.raw_text)
            
            if parsed_result.name == "Parse Failed":
                print(f"  FAILED to parse {r.name}. Keeping old data.")
                continue

            # Update resume record
            r.name = parsed_result.name
            r.email = parsed_result.email
            r.phone = parsed_result.phone
            r.skills = json.dumps(parsed_result.skills)
            r.experience = json.dumps([e.model_dump() for e in parsed_result.experience])
            r.education = json.dumps(parsed_result.education)
            r.certifications = json.dumps(parsed_result.certifications)
            r.total_years_experience = parsed_result.total_years_experience
            r.domain_expertise = json.dumps(parsed_result.domain_expertise)
            r.parsed_data = parsed_result.model_dump_json()
            
            # Post-process would have handled field_resolution and standardized_skills
            # We need to manually sync them because extract_resume_data doesn't persist to DB (it just returns the schema)
            # Actually, extract_resume_data calls extraction_agent which DOES persist new common items in post_process
            # but we need to update the Resume record's standardized columns from the returned schema.
            
            r.field_resolution = parsed_result.field_resolution.model_dump_json()
            r.standardized_skills = json.dumps(parsed_result.standardized_skills)
            r.standardized_education = json.dumps(parsed_result.standardized_education)
            r.parse_status = "success"
            
            db.commit()
            print(f"  SUCCESS: {r.name} updated.")

        print("\nAll resumes re-parsed successfully!")
    except Exception as e:
        print(f"Error during re-parsing: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(reparse_all())

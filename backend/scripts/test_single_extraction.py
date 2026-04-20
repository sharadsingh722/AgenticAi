import asyncio
import sys
import os
import json

# Add current directory to sys.path first to avoid conflicts with global 'app' modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.database import SessionLocal
from app.models import Resume
from app.services.llm_extractor import extract_resume_data

async def run_extraction_check():
    db = SessionLocal()
    try:
        # Vishwa Nath Prasher (ID: 6)
        r = db.query(Resume).filter(Resume.id == 6).first()
        if not r:
            print("Resume not found.")
            return

        print(f"Testing extraction for {r.name}...")
        parsed_result = await extract_resume_data(r.raw_text)
        
        print("\n=== Extracted Education ===")
        print(json.dumps(parsed_result.education, indent=2))
        
        print("\n=== Standardized Education ===")
        print(json.dumps(parsed_result.standardized_education, indent=2))
        
        print("\n=== Field Resolution (Education) ===")
        edu_res = parsed_result.field_resolution.education_source
        print(json.dumps(edu_res, indent=2))

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

def test_extraction():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_extraction_check())


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_extraction_check())

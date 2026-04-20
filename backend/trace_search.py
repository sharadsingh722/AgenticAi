import sys
import os
import json

# Add backend to path
sys.path.append(os.path.abspath('d:/agentic project/resume_tender_match_agent/backend'))

from app.tools.db_tools import sql_query_resumes, _resolve_common_values, _load_common_items
from app.database import SessionLocal

def trace_it():
    db = SessionLocal()
    try:
        education_items = _load_common_items(db, "education")
        
        print("--- Resolving 'PhD' ---")
        resolved = _resolve_common_values("education", "PhD", education_items)
        print(f"Resolved PhD to: {resolved}")
        
        print("\n--- Resolving 'Master' ---")
        resolved_master = _resolve_common_values("education", "Master", education_items)
        print(f"Resolved Master to: {resolved_master}")

        print("\n--- Resolving 'Civil Eng' (Skills) ---")
        skill_items = _load_common_items(db, "skills")
        resolved_skills = _resolve_common_values("skills", "Civil Eng", skill_items)
        print(f"Resolved Skills to: {resolved_skills}")

        print("\n--- Full Tool Call Simulation ---")
        result = sql_query_resumes.func(education="PhD", domain="Civil Engineering")
        print(result)

    finally:
        db.close()

if __name__ == "__main__":
    trace_it()

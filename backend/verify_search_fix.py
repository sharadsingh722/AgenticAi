import sys
import os
import json

# Add backend to path
sys.path.append(os.path.abspath('d:/agentic project/resume_tender_match_agent/backend'))

from app.tools.db_tools import sql_query_resumes

def verify_fix():
    print("--- Testing PhD vs Master Comparison ---")
    # Call the underlying function of the tool
    result = sql_query_resumes.func(education="PhD vs Master candidates in Civil Eng")
    print(result)

    if "Hosh Ram Yadav" in result:
        print("\nSUCCESS: PhD Candidate found!")
    else:
        print("\nFAILURE: PhD Candidate still missing.")

if __name__ == "__main__":
    verify_fix()

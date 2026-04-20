
import sys
import os
import json

# Add the current directory to sys.path so we can import 'app'
sys.path.append(os.getcwd())

from app.tools.db_tools import sql_query_resumes
from app.database import SessionLocal

def test_domain_it():
    print("Testing sql_query_resumes.invoke(domain='it')...")
    # Call the underlying function or use invoke
    result = sql_query_resumes.invoke({"domain": "it"})
    print("\nResult:")
    # print only names for brevity
    try:
        data = json.loads(result)
        names = [r['name'] for r in data]
        print(f"Candidates found ({len(names)}): {names}")
    except:
        print(result)

if __name__ == "__main__":
    test_domain_it()

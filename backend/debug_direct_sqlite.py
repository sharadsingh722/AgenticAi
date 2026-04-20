
import sqlite3
import json
import re

DB_PATH = 'd:/agentic project/resume_tender_match_agent/backend/data/resume_tender.db'

def normalize(value):
    if not value: return ""
    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9\s]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized

def test_sqlite_direct():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Check Common Education
    cursor.execute('SELECT name, level, aliases FROM common_education')
    items = cursor.fetchall()
    print(f"Total Common Education: {len(items)}")
    
    masters_items = [name for name, level, aliases in items if level == 'postgraduate']
    print(f"\nItems with level='postgraduate':\n{masters_items}")
    
    # 2. Check Resumes
    cursor.execute('SELECT id, name, standardized_education FROM resumes')
    resumes = cursor.fetchall()
    print(f"\nTotal Resumes: {len(resumes)}")
    
    candidates_with_masters = []
    for r_id, r_name, std_edu_json in resumes:
        std_edu = json.loads(std_edu_json) if std_edu_json else []
        matches = [val for val in std_edu if val in masters_items]
        if matches:
            candidates_with_masters.append(f"{r_name} (ID:{r_id}) -> {matches}")
            
    print(f"\nCandidates with Master's according to DB logic:\n" + "\n".join(candidates_with_masters))
    
    conn.close()

if __name__ == "__main__":
    test_sqlite_direct()

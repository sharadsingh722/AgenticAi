
import sqlite3
import json

DB_PATH = 'd:/agentic project/resume_tender_match_agent/backend/data/resume_tender.db'

def check_candidates():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name, total_years_experience, experience FROM resumes WHERE name LIKE '%Harshit%' OR name LIKE '%Tania%'")
    rows = cursor.fetchall()
    
    for r_id, name, years, exp_json in rows:
        print(f"\nID: {r_id} | Name: {name} | Years: {years}")
        exp = json.loads(exp_json)
        print("Experience Items:")
        for i, item in enumerate(exp):
            role = item.get('role', 'N/A')
            comp = item.get('company', 'N/A')
            dur = item.get('duration', 'N/A')
            print(f"  {i+1}. {role} at {comp} ({dur})")
            
    conn.close()

if __name__ == "__main__":
    check_candidates()

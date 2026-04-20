import sqlite3
import json

db_path = 'd:/agentic project/resume_tender_match_agent/backend/data/resume_tender.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT id, standardized_education, standardized_skills, domain_expertise FROM resumes")
rows = cursor.fetchall()

for row in rows:
    res_id, edu, skills, existing_domain = row
    
    edu_list = json.loads(edu) if edu else []
    skills_list = json.loads(skills) if skills else []
    domain_list = json.loads(existing_domain) if existing_domain else []
    
    # Extract domains from education keys (e.g., btech_civil -> civil)
    new_domains = set(domain_list)
    for e in edu_list:
        if 'civil' in e.lower():
            new_domains.add("civil engineering")
        if 'computer' in e.lower() or 'it' in e.lower():
            new_domains.add("it/software")
            
    # Add standardized skills that look like domains
    for s in skills_list:
        if s.lower() == 'civil engineering':
            new_domains.add("civil engineering")
            
    if len(new_domains) > len(domain_list):
        print(f"Updating ID {res_id}: {domain_list} -> {list(new_domains)}")
        cursor.execute("UPDATE resumes SET domain_expertise = ? WHERE id = ?", (json.dumps(list(new_domains)), res_id))

conn.commit()
conn.close()
print("Domain Synchronization Complete.")

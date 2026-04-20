import sqlite3
import os

db_path = 'd:/agentic project/resume_tender_match_agent/backend/data/resume_tender.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("--- Tables ---")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
for row in cursor.fetchall():
    print(row[0])

print("\n--- PhD Education Catalog ---")
cursor.execute("SELECT id, name, aliases, level FROM common_education WHERE name LIKE '%phd%' OR level='phd'")
for row in cursor.fetchall():
    print(row)

print("\n--- Candidate 8 (Hosh Ram Yadav) Profile ---")
cursor.execute("SELECT id, name, education, standardized_education FROM resumes WHERE id=8")
row = cursor.fetchone()
print(row)

conn.close()

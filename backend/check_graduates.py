import sqlite3
import os

db_path = os.path.join(os.getcwd(), 'data', 'resume_tender.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute('SELECT name, level FROM common_education WHERE level="graduate"')
rows = cursor.fetchall()
print(f"Total Graduate Items: {len(rows)}")
for row in rows:
    print(f"- {row[0]}")
conn.close()

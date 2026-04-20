
import sqlite3
import json

def check_mca():
    conn = sqlite3.connect('d:/agentic project/resume_tender_match_agent/backend/data/resume_tender.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name, level, aliases FROM common_education')
    rows = cursor.fetchall()
    for row in rows:
        if 'mca' in row[0].lower():
            print(f"Name: {row[0]}, Level: {row[1]}, Aliases: {row[2]}")
    conn.close()

if __name__ == "__main__":
    check_mca()

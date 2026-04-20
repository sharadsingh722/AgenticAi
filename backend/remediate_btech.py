import sqlite3
import json

db_path = 'd:/agentic project/resume_tender_match_agent/backend/data/resume_tender.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Get aliases from the ad-hoc key
cursor.execute("SELECT aliases FROM common_education WHERE name='graduate_degree_equivalent_bu_anniversary_1994'")
row = cursor.fetchone()
if not row:
    print("Ad-hoc key not found. Already remediated?")
    conn.close()
    exit()

adhoc_aliases = json.loads(row[0])
print(f"Ad-hoc Aliases: {adhoc_aliases}")

# 2. Get current btech_civil aliases
cursor.execute("SELECT aliases FROM common_education WHERE name='btech_civil'")
row = cursor.fetchone()
btech_aliases = json.loads(row[0])
print(f"Existing BTech Aliases: {btech_aliases}")

# 3. Merge aliases
new_aliases = list(set(btech_aliases + adhoc_aliases))
print(f"Merged Aliases: {new_aliases}")

# 4. Update btech_civil with merged aliases
cursor.execute("UPDATE common_education SET aliases = ? WHERE name = 'btech_civil'", (json.dumps(new_aliases),))

# 5. Update Sanjiv Ranjan (ID 5)
# Note: He might have other education, so we replace the specific key in the list
cursor.execute("SELECT standardized_education FROM resumes WHERE id = 5")
row = cursor.fetchone()
if row:
    edu_list = json.loads(row[0])
    new_edu_list = [e if e != 'graduate_degree_equivalent_bu_anniversary_1994' else 'btech_civil' for e in edu_list]
    print(f"Updating Sanjiv Ranjan Education: {edu_list} -> {new_edu_list}")
    cursor.execute("UPDATE resumes SET standardized_education = ? WHERE id = 5", (json.dumps(new_edu_list),))

# 6. Delete the ad-hoc key
cursor.execute("DELETE FROM common_education WHERE name = 'graduate_degree_equivalent_bu_anniversary_1994'")
print("Deleted ad-hoc key.")

conn.commit()
conn.close()
print("Remediation Complete.")

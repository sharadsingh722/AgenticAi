import json
import os

def fix_db_tools():
    path = 'app/tools/db_tools.py'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    old_rules_start = '        "1. DUAL-LEVEL RULE (PRIORITY): Updated for test.\\n"'
    old_rules_end = '        "5. Output: Return ONLY the list of matching technical identifiers (names)."'
    
    # We find the start and end of the block we want to replace
    start_idx = content.find(old_rules_start)
    end_idx = content.find(old_rules_end) + len(old_rules_end)
    
    if start_idx == -1:
        print("Could not find start index")
        return
    if end_idx < start_idx:
        print("Could not find end index")
        return

    new_rules = """        "1. INTENT DISCOVERY: Identify the 'Degree Family' (e.g. Engineering, Management, Computer Applications) and 'Academic Level' (Graduate/Postgrad) from the User Filter.\\n"
        "2. DUAL-LEVEL RULE: The level 'level_graduate_and_postgraduate' is a superset. SELECT it ONLY IF the 'Degree Family' also matches. \\n"
        "   - Example: If filter is 'BTech' (Engineering Graduate), do NOT select 'MCA Integrated' (Computer Applications Dual), but DO select 'BTech-MTech Integrated' if it exists.\\n"
        "3. SUBJECT/DOMAIN MATCH: If the filter implies a specific field (e.g. 'Civil'), prioritize entries matching that field.\\n"
        "4. EXPLICIT DEGREE MATCH: If a specific abbreviation (BTech, BE, MCA, MBA) is used, ensure the selected identifiers are strictly within that degree's family.\\n"
        "5. Output: Return ONLY the list of matching technical identifiers (names) as JSON.\""""
    
    new_content = content[:start_idx] + new_rules + content[end_idx:]
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Successfully updated db_tools.py")

if __name__ == "__main__":
    fix_db_tools()

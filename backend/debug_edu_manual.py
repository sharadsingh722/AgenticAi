
import sys
import os
import json

# Add the current directory to sys.path so we can import 'app'
sys.path.append(os.getcwd())

from app.tools.db_tools import _load_common_items, _fallback_resolve_common_values
from app.database import SessionLocal

def test_edu_manual():
    db = SessionLocal()
    try:
        items = _load_common_items(db, "education")
        print(f"Loaded {len(items)} education items.")
        
        query = "masters"
        # Manual fallback test
        resolved_fallback = _fallback_resolve_common_values("education", query, items)
        print(f"\nQuery: '{query}'")
        print(f"Fallback Resolved: {resolved_fallback}")
        
        # Check all Postgraduate items
        pg_items = [i['name'] for i in items if i.get('level') == 'postgraduate']
        print(f"\nAll Postgraduate Items in DB: {pg_items}")
        
    finally:
        db.close()

if __name__ == "__main__":
    test_edu_manual()

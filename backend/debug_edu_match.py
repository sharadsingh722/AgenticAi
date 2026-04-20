
import sys
import os

# Add the current directory to sys.path so we can import 'app'
sys.path.append(os.getcwd())

from app.tools.db_tools import _resolve_common_values, _load_common_items
from app.database import SessionLocal

def test_edu_resolution():
    db = SessionLocal()
    try:
        items = _load_common_items(db, "education")
        print(f"Loaded {len(items)} education items.")
        
        query = "masters"
        resolved = _resolve_common_values("education", query, items)
        print(f"\nQuery: '{query}'")
        print(f"Resolved: {resolved}")
        
    finally:
        db.close()

if __name__ == "__main__":
    test_edu_resolution()

import sys
import os
import json
import asyncio

# Setup path
sys.path.append(os.getcwd())

from app.database import SessionLocal
from app.tools.db_tools import _load_common_items, _resolve_common_values

async def test_resolution():
    db = SessionLocal()
    try:
        education_items = _load_common_items(db, "education")
        user_query = "BTech"
        resolved = _resolve_common_values("education", user_query, education_items)
        print(f"Query: {user_query}")
        print(f"Resolved Common Values: {resolved}")
        
        if "mca_integrated" in resolved:
            print("FAILED: mca_integrated still found in BTech results")
        else:
            print("SUCCESS: mca_integrated excluded from BTech results")
            
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_resolution())

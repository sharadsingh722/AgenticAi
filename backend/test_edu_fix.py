import sys
import os
sys.path.append(os.getcwd())

from app.database import SessionLocal
from app.tools.db_tools import _load_common_items, _resolve_common_values


def test_resolution():
    db = SessionLocal()
    try:
        education_items = _load_common_items(db, "education")
        user_query = "BTech"
        resolved = _resolve_common_values("education", user_query, education_items)
        assert "mca_integrated" not in resolved
        assert any(value.startswith("btech_") or value == "btech_civil" for value in resolved)
    finally:
        db.close()

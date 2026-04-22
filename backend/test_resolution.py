import os
import sys

sys.path.append(os.getcwd())

from app.tools.db_tools import _resolve_common_values


def test_resolution():
    catalog = [
        {"name": "btech_civil", "display_label": "btech civil", "level": "graduate", "aliases": [], "search_terms": ["civil engineering"], "concepts": ["civil engineering"]},
        {"name": "mtech_civil", "display_label": "mtech civil", "level": "postgraduate", "aliases": [], "search_terms": ["civil engineering"], "concepts": ["civil engineering"]},
        {"name": "phd_civil_engineering", "display_label": "phd civil engineering", "level": "phd", "aliases": ["Doctor of Philosophy in Civil Engineering"], "search_terms": ["civil engineering"], "concepts": ["civil engineering"]},
        {"name": "mtech_structural", "display_label": "mtech structural", "level": "postgraduate", "aliases": [], "search_terms": ["structural engineering"], "concepts": ["structural engineering"]},
    ]

    resolved = _resolve_common_values("education", "PhD vs Master candidates in Civil Eng", catalog)

    assert "phd_civil_engineering" in resolved
    assert "mtech_civil" in resolved
    assert "btech_civil" not in resolved

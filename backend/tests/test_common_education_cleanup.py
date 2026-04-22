import os
import sys

current_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app.agents.extraction_agent import (
    _clean_education_raw_value,
    _derive_education_key,
    _is_likely_education_value,
)


def test_non_education_tender_phrase_is_rejected():
    assert not _is_likely_education_value("be accordance with the procedure")


def test_noisy_degree_text_is_preserved_as_education():
    value = "Graduate/Degree in Engineering or Equivalent in CIVIL from Bangalore University, 1994"
    assert _is_likely_education_value(value)


def test_education_cleaner_removes_file_view_noise():
    raw = "Post Graduate MSC Geology University of Pune 1988 1593 -- Download View Pune File"
    cleaned = _clean_education_raw_value(raw)
    assert "download" not in cleaned.lower()
    assert "file" not in cleaned.lower()
    assert "MSC Geology" in cleaned


def test_derive_education_key_prefers_compact_degree_subject_slug():
    raw = "Bachelor of Engineering (B.E.), Civil Engineering, Jawaharlal Nehru Technological University, Kakinada, 1995"
    assert _derive_education_key(raw) == "btech_civil"

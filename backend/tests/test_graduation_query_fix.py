import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from app.tools.db_tools import _education_entry_matches_query, _interpret_resume_query


def test_graduation_query_is_interpreted_as_education():
    interpretation = _interpret_resume_query("List all the candidates who have done graduation")
    assert interpretation.education_query is not None


def test_dotted_bca_and_mca_match_graduation():
    assert _education_entry_matches_query(
        "B.C.A. - Computer Applications - Computer Applications (Full Time) | Percentage : 70.97 / 100",
        "graduation",
    )
    assert _education_entry_matches_query(
        "M.C.A. - Computer Applications - 2 Years | Percentage: 69.60 / 100",
        "postgraduation",
    )

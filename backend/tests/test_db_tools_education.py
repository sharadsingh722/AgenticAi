# Add current directory to sys.path first to avoid conflicts with global 'app' modules
import os
import sys

current_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app.tools.db_tools import (
    _education_entry_matches_query,
    _education_raw_query_patterns,
    _education_semantic_terms,
)


def test_btech_semantics_do_not_match_generic_be_prefix_text():
    assert "bachelor_engineering" in _education_semantic_terms("BTech")
    assert "bachelor_engineering" not in _education_semantic_terms("be accordance with the procedure")


def test_btech_raw_patterns_include_resume_friendly_variants():
    patterns = _education_raw_query_patterns("BTech")
    assert "b.tech" in patterns
    assert "b tech" in patterns
    assert "bachelor of technology" in patterns


def test_graduation_query_matches_multiple_bachelor_degree_variants():
    assert _education_entry_matches_query("BE Civil Engineering, University of Delhi, 1986", "graduation")
    assert _education_entry_matches_query("BSC, Amravati University, 1986", "graduation")
    assert not _education_entry_matches_query("PhD, IIT Delhi, 2005", "graduation")


def test_post_graduation_query_matches_only_postgraduate_entries():
    assert _education_entry_matches_query("M.Tech in Structural Engineering, 1993", "post graduation")
    assert not _education_entry_matches_query("BE Civil Engineering, University of Delhi, 1986", "post graduation")

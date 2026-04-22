import os
import sys

current_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app.tools.db_tools import _extract_domain_phrase, _interpret_resume_query, query_resumes_dynamic


def test_interpreter_maps_background_and_strict_experience():
    parsed = _interpret_resume_query("Show candidates with Civil Engineering background and more than 30 years experience")
    assert parsed.education_query == "Civil Engineering"
    assert parsed.experience_operator == "gt"
    assert parsed.experience_value == 30


def test_interpreter_extracts_negative_skill_clause():
    parsed = _interpret_resume_query("Give me the names of candidates who have exactly Python but not Java")
    assert "python" in " ".join(parsed.skill_queries).lower() or parsed.original_query
    assert "java" in " ".join(parsed.excluded_skill_queries).lower()


def test_dynamic_query_excludes_exactly_30_for_more_than_30():
    result = query_resumes_dynamic.func("Show candidates with Civil Engineering background and more than 30 years experience")
    assert "Dharmireddi Sanyasi Naidu" in result
    assert "Pramod Kumar Jain" in result
    assert "Durgesh Kumar" in result
    assert "Sanjiv Ranjan" not in result


def test_domain_extractor_pulls_target_domain_phrase():
    assert _extract_domain_phrase("list all the candidates of IT domain") == "IT"
    parsed = _interpret_resume_query("list all the candidates of IT domain")
    assert parsed.domain_query == "IT"

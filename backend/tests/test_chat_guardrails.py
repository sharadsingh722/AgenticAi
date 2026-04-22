import os
import sys
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Resume, Tender, ChatMessage
from app.routers.chat import (
    _build_grounded_factual_response,
    _extract_name_prefix_filter,
    _history_has_project_context,
    _is_contextual_followup_query,
    _is_project_scoped_query,
    _off_topic_response,
)


def test_off_topic_query_is_blocked():
    assert _is_project_scoped_query("what is agentic ai") is False
    assert "MatchOps AI is scoped to this workspace only." in _off_topic_response()


def test_workspace_queries_are_allowed():
    assert _is_project_scoped_query("show all candidate names") is True
    assert _is_project_scoped_query("best-fit candidates for tender id 1") is True
    assert _is_project_scoped_query("find resumes with python skills") is True


def test_extract_name_prefix_filter_for_candidate_name_queries():
    assert _extract_name_prefix_filter("how many candidates name start with H") == "H"
    assert _extract_name_prefix_filter("List candidates whose names start with 'Ha'") == "Ha"
    assert _extract_name_prefix_filter("Show resumes where name starts with Har") == "Har"
    assert _extract_name_prefix_filter("find civil engineers") is None


def _seed_test_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.add_all([
        Resume(
            id=1,
            name="Hosh Ram Yadav",
            raw_text="resume 1",
            file_name="hosh.pdf",
            total_years_experience=33,
            skills=json.dumps(["Bridge Design", "AutoCAD"]),
            education=json.dumps(["B.E. Civil"]),
            parsed_data=json.dumps({"experience": [{"role": "Assistant Engineer", "company": "ABC", "duration": "10 years"}]}),
        ),
        Resume(
            id=2,
            name="Harshit Punera",
            raw_text="resume 2",
            file_name="harshit.pdf",
            total_years_experience=0,
            skills=json.dumps(["Python"]),
            education=json.dumps(["MCA"]),
            parsed_data=json.dumps({"experience": []}),
        ),
        Tender(
            id=4,
            project_name="Bridge Rehabilitation Project",
            client="PWD",
            raw_text="tender 4",
            file_name="tender.pdf",
            required_roles=json.dumps([{"role_title": "Bridge Engineer", "min_experience": 8}]),
            key_technologies=json.dumps(["AutoCAD", "STAAD"]),
        ),
        Tender(
            id=5,
            project_name="Latest Highway Project",
            client="NHAI",
            raw_text="tender 5",
            file_name="latest-tender.pdf",
            required_roles=json.dumps([{"role_title": "Project Manager", "min_experience": 5}]),
            key_technologies=json.dumps(["HAM", "DBOT"]),
            created_at=datetime.utcnow() + timedelta(seconds=1),
        ),
    ])
    db.commit()
    return db


def test_grounded_factual_response_for_resume_list_and_count():
    db = _seed_test_session()
    try:
        count_response, count_log = _build_grounded_factual_response("how many resumes do we have", db)
        assert "There are 2 resumes" in count_response
        assert count_log[0]["tool"] == "live_resume_inventory_lookup"

        list_response, list_log = _build_grounded_factual_response("show all candidate names", db)
        assert "Hosh Ram Yadav" in list_response
        assert "Harshit Punera" in list_response
        assert list_log[0]["tool"] == "live_resume_inventory_lookup"
    finally:
        db.close()


def test_grounded_factual_response_for_detail_queries():
    db = _seed_test_session()
    try:
        resume_response, resume_log = _build_grounded_factual_response("show resume details for candidate id 1", db)
        assert "**Hosh Ram Yadav**" in resume_response
        assert "Assistant Engineer" in resume_response
        assert resume_log[0]["tool"] == "live_resume_detail_lookup"

        tender_response, tender_log = _build_grounded_factual_response("show tender details for TND-0004", db)
        assert "**TND-0004**" in tender_response
        assert "Bridge Rehabilitation Project" in tender_response
        assert tender_log[0]["tool"] == "live_tender_detail_lookup"
    finally:
        db.close()


def test_filtered_queries_do_not_use_simple_inventory_shortcut():
    db = _seed_test_session()
    try:
        response, tool_log = _build_grounded_factual_response("how many python resumes do we have", db)
        assert response == ""
        assert tool_log == []
    finally:
        db.close()


def test_scope_guard_accepts_typoed_project_queries():
    assert _is_project_scoped_query("give me remue details of harsh") is True
    assert _is_project_scoped_query("matcihing list") is True


def test_contextual_followup_allowed_when_history_has_project_context():
    prior_history = [
        ChatMessage(role="assistant", content="Here are tender details", tool_calls=json.dumps([{"tool": "get_tender_detail"}])),
    ]
    assert _history_has_project_context(prior_history) is True
    assert _is_contextual_followup_query("hindi mai batao") is True


def test_grounded_response_returns_latest_tender_details():
    db = _seed_test_session()
    try:
        response, tool_log = _build_grounded_factual_response("recently uploaded tender details", db)
        assert "Latest Highway Project" in response
        assert tool_log[0]["tool"] == "live_tender_detail_lookup"
    finally:
        db.close()

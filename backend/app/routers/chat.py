"""Chat router with streaming responses from the chat agent."""
import json
from datetime import datetime
import difflib
import logging
import re
import traceback
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, AIMessage

from app.database import get_db
from app.models import ChatMessage, ChatSession, Resume, Tender
from app.schemas import ChatRequest, ChatMessageResponse, ChatSessionResponse
from app.agents.chat_agent import chat_agent
from app.utils.streaming import sse_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


PROJECT_SCOPE_TERMS = {
    "resume", "resumes", "candidate", "candidates", "cv", "cvs", "profile", "profiles",
    "tender", "tenders", "bid", "bids", "rfp", "proposal", "proposals", "project", "projects",
    "matching", "match", "shortlist", "inventory", "skill", "skills", "education", "experience",
    "qualification", "qualifications", "document", "documents", "count", "counts", "name", "names",
    "role", "roles", "engineer", "engineers", "resume id", "tender id", "compare", "comparison",
}

PROJECT_SCOPE_PHRASES = (
    "best fit",
    "top candidates",
    "candidate names",
    "resume details",
    "tender details",
    "system stats",
    "match results",
    "uploaded resume",
    "uploaded tender",
)

SYSTEM_META_TERMS = {
    "prompt", "prompts", "logic", "routing", "route", "history", "context", "dynamic",
    "hardcode", "hardcoded", "workflow", "query", "queries", "response", "behavior",
    "behaviour", "agent", "tool", "tools", "followup", "followups",
}

FOLLOWUP_TERMS = {
    "hindi", "english", "translate", "translation", "explain", "detail", "details", "more",
    "thoda", "aur", "batao", "batana", "isme", "isse", "iske", "uske", "iska", "tell",
    "ye", "yeh", "this", "that", "these", "those", "them", "all", "sab", "unka", "unki",
    "unke", "unko", "inko", "usme", "usmein", "ismein", "compare", "comparison",
}

NAME_PREFIX_PATTERNS = (
    re.compile(
        r"\b(?:how many|count|list|show|which|who are)\b.*?\b(?:candidate|candidates|resume|resumes)\b.*?\bname(?:s)?\b.*?\bstart(?:s)? with\b\s*[\"']?([a-z0-9][a-z0-9\s.-]*)[\"']?",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:candidate|candidates|resume|resumes)\b.*?\bwhose\b.*?\bname(?:s)?\b.*?\bstart(?:s)? with\b\s*[\"']?([a-z0-9][a-z0-9\s.-]*)[\"']?",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bname(?:s)?\b.*?\bstart(?:s)? with\b\s*[\"']?([a-z0-9][a-z0-9\s.-]*)[\"']?",
        re.IGNORECASE,
    ),
)

RESUME_TERMS = {"resume", "resumes", "candidate", "candidates", "cv", "cvs", "profile", "profiles"}
TENDER_TERMS = {"tender", "tenders", "bid", "bids", "rfp", "rfps", "proposal", "proposals", "project", "projects"}
LIST_TERMS = {"list", "show", "all", "which", "who", "available", "available?"}
COUNT_TERMS = {"count", "counts", "many", "total", "number"}
DETAIL_TERMS = {"detail", "details", "about", "info", "information", "show", "open"}
DOCUMENT_FACT_TERMS = {
    "who", "whose", "contact", "person", "email", "phone", "telephone", "mobile", "address",
    "deadline", "emd", "clause", "clauses", "eligibility", "submission", "bid", "signed",
    "signatory", "officer", "authority", "reference", "fax", "communication",
}
COMPLEX_FILTER_MARKERS = {
    "experience", "skills", "skill", "education", "qualification", "domain", "certification",
    "compare", "comparison", "best", "fit", "top", "match", "matching", "more", "less",
    "greater", "between", "minimum", "minimums", "background", "expert", "expertise",
}
FILLER_TERMS = {
    "a", "an", "the", "do", "we", "have", "current", "live", "workspace", "in", "our", "of",
    "for", "please", "give", "me", "what", "is", "are", "there", "tell", "fetch", "get",
    "need", "want", "available", "inventory", "all", "show", "list", "many", "how", "total",
    "number", "count", "counts", "names", "name", "whose", "start", "starts", "with",
}


def _is_project_scoped_query(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return True

    normalized = re.sub(r"[^a-z0-9\s]+", " ", text)
    if any(phrase in normalized for phrase in PROJECT_SCOPE_PHRASES):
        return True

    tokens = {token for token in normalized.split() if token}
    if tokens & PROJECT_SCOPE_TERMS:
        return True

    fuzzy_scope_vocab = [term for term in PROJECT_SCOPE_TERMS if " " not in term and len(term) >= 4]
    for token in tokens:
        if len(token) < 4:
            continue
        if difflib.get_close_matches(token, fuzzy_scope_vocab, n=1, cutoff=0.72):
            return True

    # Allow direct ID-based lookups even if the phrasing is short.
    if re.search(r"\b(?:id|tnd)[-\s:]?\d+\b", normalized):
        return True

    return False


def _is_meta_system_query(message: str) -> bool:
    normalized = _normalize_query_text(message)
    if not normalized:
        return False
    tokens = set(normalized.split())
    return bool(tokens & SYSTEM_META_TERMS)


def _off_topic_response() -> str:
    return (
        "MatchOps AI is scoped to this workspace only. I can help with resumes, tenders, "
        "candidate search, inventory counts, comparisons, and tender-resume matching.\n\n"
        "Try queries like:\n"
        "- Show all candidate names\n"
        "- Find Civil Engineering candidates with more than 10 years experience\n"
        "- List all tenders\n"
        "- Show best-fit candidates for tender ID 1"
    )


def _extract_name_prefix_filter(message: str) -> str | None:
    text = (message or "").strip()
    if not text:
        return None

    for pattern in NAME_PREFIX_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        prefix = re.sub(r"\s+", " ", match.group(1)).strip(" .?!,;:\"'")
        if prefix:
            return prefix
    return None


def _is_contextual_followup_query(message: str) -> bool:
    normalized = _normalize_query_text(message)
    if not normalized:
        return False

    tokens = normalized.split()
    if len(tokens) <= 10 and any(term in tokens for term in FOLLOWUP_TERMS):
        return True

    followup_patterns = (
        "hindi mai",
        "english me",
        "more details",
        "list all of them",
        "show all of them",
        "all of them",
        "list them",
        "show them",
        "aur batao",
        "thoda or",
        "thoda aur",
        "give more details",
        "best match",
        "iske bare",
        "iske baare",
        "uske bare",
        "uske baare",
        "tell me more",
        "show more",
        "compare them",
    )
    return any(pattern in normalized for pattern in followup_patterns)


def _history_has_project_context(history: list[ChatMessage]) -> bool:
    recent_messages = history[-8:]
    for msg in recent_messages:
        if msg.role == "assistant" and msg.tool_calls:
            return True
        if msg.role == "user" and _is_project_scoped_query(msg.content):
            return True
    return False


def _should_treat_as_scoped_with_history(message: str, has_project_context: bool) -> bool:
    if not has_project_context:
        return False
    return _is_contextual_followup_query(message) or _is_meta_system_query(message)


def _normalize_query_text(message: str) -> str:
    return re.sub(r"[^a-z0-9\s]+", " ", (message or "").strip().lower()).strip()


def _query_tokens(message: str) -> set[str]:
    normalized = _normalize_query_text(message)
    return {token for token in normalized.split() if token}


def _has_any_token(tokens: set[str], options: set[str]) -> bool:
    return bool(tokens & options)


def _is_complex_resume_query(message: str) -> bool:
    tokens = _query_tokens(message)
    normalized = _normalize_query_text(message)
    if _extract_name_prefix_filter(message):
        return False
    if any(marker in normalized for marker in ("show all", "list all", "who are all", "candidate names", "resume names")):
        return False
    return _has_any_token(tokens, COMPLEX_FILTER_MARKERS)


def _has_extra_filter_tokens(message: str, entity_terms: set[str]) -> bool:
    tokens = _query_tokens(message)
    allowed = entity_terms | LIST_TERMS | COUNT_TERMS | DETAIL_TERMS | FILLER_TERMS
    if "id" in tokens:
        allowed = allowed | {"id"}

    extras = {
        token for token in tokens
        if token not in allowed and not token.isdigit()
    }
    return bool(extras)


def _is_simple_resume_inventory_query(message: str) -> bool:
    tokens = _query_tokens(message)
    normalized = _normalize_query_text(message)
    has_resume_terms = _has_any_token(tokens, RESUME_TERMS)
    asks_count = _has_any_token(tokens, COUNT_TERMS) or "how many" in normalized
    asks_list = _has_any_token(tokens, LIST_TERMS) or "show all" in normalized or "list all" in normalized
    asks_names = "name" in tokens or "names" in tokens
    return (
        has_resume_terms
        and not _is_complex_resume_query(message)
        and not _has_extra_filter_tokens(message, RESUME_TERMS)
        and (asks_count or asks_list or asks_names)
    )


def _is_simple_tender_inventory_query(message: str) -> bool:
    tokens = _query_tokens(message)
    normalized = _normalize_query_text(message)
    has_tender_terms = _has_any_token(tokens, TENDER_TERMS)
    asks_count = _has_any_token(tokens, COUNT_TERMS) or "how many" in normalized
    asks_list = _has_any_token(tokens, LIST_TERMS) or "show all" in normalized or "list all" in normalized
    asks_names = "name" in tokens or "names" in tokens
    return (
        has_tender_terms
        and not _has_extra_filter_tokens(message, TENDER_TERMS)
        and (asks_count or asks_list or asks_names)
    )


def _is_simple_detail_lookup(message: str) -> bool:
    tokens = _query_tokens(message)
    normalized = _normalize_query_text(message)
    asks_detail = _has_any_token(tokens, DETAIL_TERMS)
    asks_only_detail = asks_detail and len(tokens) <= 10
    asks_document_fact = bool(tokens & DOCUMENT_FACT_TERMS)
    resume_id = _extract_resume_id(message)
    tender_id = _extract_tender_id(message)
    has_resume_terms = _has_any_token(tokens, RESUME_TERMS)
    has_tender_terms = _has_any_token(tokens, TENDER_TERMS)
    simple_resume_detail = (
        resume_id is not None
        and has_resume_terms
        and asks_only_detail
        and not asks_document_fact
        and not _has_extra_filter_tokens(message, RESUME_TERMS)
    )
    simple_tender_detail = (
        tender_id is not None
        and has_tender_terms
        and asks_only_detail
        and not asks_document_fact
        and not _has_extra_filter_tokens(message, TENDER_TERMS)
    )
    return simple_resume_detail or simple_tender_detail


def _should_use_grounded_response(message: str) -> bool:
    normalized = _normalize_query_text(message)
    if _extract_name_prefix_filter(message):
        return True

    if _is_simple_detail_lookup(message):
        return True

    if _is_simple_resume_inventory_query(message) or _is_simple_tender_inventory_query(message):
        return True

    if (
        any(marker in normalized for marker in ("last", "latest", "recent", "recently", "uploaded"))
        and not _has_extra_filter_tokens(message, TENDER_TERMS)
        and not _is_complex_resume_query(message)
    ):
        return True

    return False


def _extract_resume_id(message: str) -> int | None:
    normalized = _normalize_query_text(message)
    match = re.search(r"\b(?:resume|candidate|profile)\s+id\s+(\d+)\b", normalized)
    if match:
        return int(match.group(1))
    match = re.search(r"\bid\s+(\d+)\b", normalized)
    if match and _has_any_token(_query_tokens(message), RESUME_TERMS):
        return int(match.group(1))
    return None


def _extract_tender_id(message: str) -> int | None:
    normalized = _normalize_query_text(message)
    tnd_match = re.search(r"\btnd[\s-]?0*(\d+)\b", normalized)
    if tnd_match:
        return int(tnd_match.group(1))
    match = re.search(r"\b(?:tender|project|proposal|bid)\s+id\s+(\d+)\b", normalized)
    if match:
        return int(match.group(1))
    match = re.search(r"\bid\s+(\d+)\b", normalized)
    if match and _has_any_token(_query_tokens(message), TENDER_TERMS):
        return int(match.group(1))
    return None


def _format_resume_role(resume: Resume) -> str:
    role = "No specified role"
    if resume.parsed_data:
        try:
            parsed = json.loads(resume.parsed_data)
            experience = parsed.get("experience", [])
            if experience and isinstance(experience, list):
                role = experience[0].get("role") or role
        except json.JSONDecodeError:
            logger.warning("Invalid parsed_data JSON for resume_id=%s", resume.id)
    return role


def _format_resume_list_item(resume: Resume) -> str:
    return (
        f"- **{resume.name}** (ID: {resume.id}) | "
        f"Role: {_format_resume_role(resume)} | "
        f"Experience: {(resume.total_years_experience or 0):g} years"
    )


def _format_tender_list_item(tender: Tender) -> str:
    return f"- **TND-{tender.id:04d}** | {tender.project_name} | Client: {tender.client or 'N/A'}"


def _build_resume_detail_response(resume_id: int, db: Session) -> tuple[str, list[dict]]:
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        return f"Resume ID {resume_id} not found in the live inventory.", [{
            "tool": "live_resume_detail_lookup",
            "input": {"resume_id": resume_id},
            "result": "No matching resume found.",
        }]

    skills = json.loads(resume.skills) if resume.skills else []
    education = json.loads(resume.education) if resume.education else []
    parsed = json.loads(resume.parsed_data) if resume.parsed_data else {}
    experience = parsed.get("experience", []) if isinstance(parsed, dict) else []

    lines = [
        f"**{resume.name}** (ID: {resume.id})",
        f"- Role: {_format_resume_role(resume)}",
        f"- Experience: {(resume.total_years_experience or 0):g} years",
        f"- Education: {', '.join(education) if education else 'N/A'}",
        f"- Skills: {', '.join(skills[:12]) if skills else 'N/A'}",
    ]
    if experience:
        lines.append("- Work History:")
        for item in experience[:5]:
            lines.append(
                f"  - {item.get('role') or 'N/A'} at {item.get('company') or 'N/A'} ({item.get('duration') or 'N/A'})"
            )

    return "\n".join(lines), [{
        "tool": "live_resume_detail_lookup",
        "input": {"resume_id": resume_id},
        "result": f"Fetched live details for resume ID {resume_id}.",
    }]


def _build_tender_detail_response(tender_id: int, db: Session) -> tuple[str, list[dict]]:
    tender = db.query(Tender).filter(Tender.id == tender_id).first()
    if not tender:
        return f"Tender ID {tender_id} not found in the live inventory.", [{
            "tool": "live_tender_detail_lookup",
            "input": {"tender_id": tender_id},
            "result": "No matching tender found.",
        }]

    roles = json.loads(tender.required_roles) if tender.required_roles else []
    techs = json.loads(tender.key_technologies) if tender.key_technologies else []
    eligibility = json.loads(tender.eligibility_criteria) if tender.eligibility_criteria else []
    lines = [
        f"**TND-{tender.id:04d}** | {tender.project_name}",
        f"- Client: {tender.client or 'N/A'}",
        f"- Duration: {tender.project_duration or 'N/A'}",
        f"- Reference: {tender.document_reference or 'N/A'}",
        f"- Date: {tender.document_date or 'N/A'}",
        f"- File: {tender.file_name}",
        f"- Technologies: {', '.join(techs) if techs else 'N/A'}",
        f"- Eligibility Criteria Count: {len(eligibility)}",
        f"- Roles Count: {len(roles)}",
    ]

    if eligibility:
        lines.append("- Eligibility Criteria:")
        for item in eligibility[:20]:
            lines.append(f"  - {item}")

    if roles:
        lines.append("- Required Roles:")
        for role in roles[:20]:
            role_title = role.get('role_title') or 'N/A'
            min_experience = role.get('min_experience', 0)
            required_skills = role.get('required_skills', []) or []
            required_certs = role.get('required_certifications', []) or []
            required_domain = role.get('required_domain', []) or []
            preferred_components = role.get('preferred_components', []) or []
            min_project_value_cr = role.get('min_project_value_cr', 0)
            client_type_pref = role.get('client_type_preference')
            lines.append(
                f"  - {role_title}"
            )
            lines.append(f"    - Min Experience: {min_experience} years")
            lines.append(f"    - Required Skills: {', '.join(required_skills) if required_skills else 'N/A'}")
            lines.append(f"    - Required Certifications: {', '.join(required_certs) if required_certs else 'N/A'}")
            lines.append(f"    - Required Domain: {', '.join(required_domain) if required_domain else 'N/A'}")
            lines.append(f"    - Preferred Components: {', '.join(preferred_components) if preferred_components else 'N/A'}")
            lines.append(f"    - Min Project Value: {min_project_value_cr or 0} Cr")
            lines.append(f"    - Client Type Preference: {client_type_pref or 'N/A'}")

    return "\n".join(lines), [{
        "tool": "live_tender_detail_lookup",
        "input": {"tender_id": tender_id},
        "result": f"Fetched live details for tender ID {tender_id}.",
    }]


def _build_latest_tender_response(message: str, db: Session) -> tuple[str, list[dict]]:
    normalized = _normalize_query_text(message)
    if "tender" not in normalized and "project" not in normalized:
        return "", []
    if not any(marker in normalized for marker in ("last", "latest", "recent", "recently", "uploaded")):
        return "", []

    tender = db.query(Tender).order_by(Tender.created_at.desc(), Tender.id.desc()).first()
    if not tender:
        return "No tenders are available in the live inventory yet.", [{
            "tool": "live_latest_tender_lookup",
            "input": {"mode": "latest"},
            "result": "No tender found in live inventory.",
        }]
    return _build_tender_detail_response(tender.id, db)


def _build_name_prefix_response(message: str, db: Session) -> tuple[str, list[dict]]:
    prefix = _extract_name_prefix_filter(message)
    if not prefix:
        return "", []

    normalized_prefix = prefix.casefold()
    resumes = db.query(Resume).order_by(Resume.id.asc()).all()
    matches = [resume for resume in resumes if (resume.name or "").casefold().startswith(normalized_prefix)]

    prefix_label = prefix.upper() if len(prefix) == 1 else prefix
    count = len(matches)
    candidate_word = "candidate" if count == 1 else "candidates"
    name_phrase = "name starts" if count == 1 else "names start"
    prefix_kind = "letter" if len(prefix) == 1 else "prefix"
    lines = [f"There {'is' if count == 1 else 'are'} {count} {candidate_word} whose {name_phrase} with the {prefix_kind} \"{prefix_label}\":"]

    for resume in matches:
        lines.append(_format_resume_list_item(resume))

    if count == 0:
        lines.append("No candidate names in the current live inventory match that prefix.")

    tool_log = [{
        "tool": "live_resume_name_prefix_lookup",
        "input": {"prefix": prefix},
        "result": f"Matched {count} resume(s) from live DB inventory.",
    }]
    return "\n".join(lines), tool_log


def _build_grounded_factual_response(message: str, db: Session) -> tuple[str, list[dict]]:
    prefix_response, prefix_tool_log = _build_name_prefix_response(message, db)
    if prefix_response:
        return prefix_response, prefix_tool_log

    latest_tender_response, latest_tender_log = _build_latest_tender_response(message, db)
    if latest_tender_response:
        return latest_tender_response, latest_tender_log

    tokens = _query_tokens(message)
    normalized = _normalize_query_text(message)
    has_resume_terms = _has_any_token(tokens, RESUME_TERMS)
    has_tender_terms = _has_any_token(tokens, TENDER_TERMS)
    asks_count = _has_any_token(tokens, COUNT_TERMS) or "how many" in normalized
    asks_list = _has_any_token(tokens, LIST_TERMS) or "show all" in normalized or "list all" in normalized
    asks_names = "name" in tokens or "names" in tokens
    asks_detail = _has_any_token(tokens, DETAIL_TERMS)

    resume_id = _extract_resume_id(message)
    tender_id = _extract_tender_id(message)

    if resume_id is not None and has_resume_terms and asks_detail:
        return _build_resume_detail_response(resume_id, db)

    if tender_id is not None and has_tender_terms and asks_detail:
        return _build_tender_detail_response(tender_id, db)

    if asks_count and has_resume_terms and has_tender_terms:
        resume_count = db.query(Resume).count()
        tender_count = db.query(Tender).count()
        return (
            "Current live system inventory:\n"
            f"- Total Resumes: {resume_count}\n"
            f"- Total Tenders: {tender_count}",
            [{
                "tool": "live_system_inventory_lookup",
                "input": {"entity": "resumes_and_tenders"},
                "result": f"Fetched live counts: resumes={resume_count}, tenders={tender_count}.",
            }],
        )

    if has_resume_terms and not _is_complex_resume_query(message) and not _has_extra_filter_tokens(message, RESUME_TERMS):
        resumes = db.query(Resume).order_by(Resume.id.asc()).all()
        if asks_count and not asks_list and not asks_names:
            return (
                f"There are {len(resumes)} resumes in the current live inventory.",
                [{
                    "tool": "live_resume_inventory_lookup",
                    "input": {"mode": "count"},
                    "result": f"Fetched live resume count: {len(resumes)}.",
                }],
            )

        if asks_list or asks_names:
            lines = [f"Current live resume inventory has {len(resumes)} candidate(s):"]
            lines.extend(_format_resume_list_item(resume) for resume in resumes)
            return "\n".join(lines), [{
                "tool": "live_resume_inventory_lookup",
                "input": {"mode": "list"},
                "result": f"Fetched {len(resumes)} resume(s) from live inventory.",
            }]

    if has_tender_terms and not _has_extra_filter_tokens(message, TENDER_TERMS):
        tenders = db.query(Tender).order_by(Tender.id.asc()).all()
        if asks_count and not asks_list:
            return (
                f"There are {len(tenders)} tenders in the current live inventory.",
                [{
                    "tool": "live_tender_inventory_lookup",
                    "input": {"mode": "count"},
                    "result": f"Fetched live tender count: {len(tenders)}.",
                }],
            )

        if asks_list or asks_names:
            lines = [f"Current live tender inventory has {len(tenders)} tender(s):"]
            lines.extend(_format_tender_list_item(tender) for tender in tenders)
            return "\n".join(lines), [{
                "tool": "live_tender_inventory_lookup",
                "input": {"mode": "list"},
                "result": f"Fetched {len(tenders)} tender(s) from live inventory.",
            }]

    return "", []


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(db: Session = Depends(get_db)):
    """List all chat sessions ordered by update time."""
    return db.query(ChatSession).order_by(ChatSession.updated_at.desc()).all()


@router.post("/sessions", response_model=ChatSessionResponse)
async def create_session(session_id: str, db: Session = Depends(get_db)):
    """Create a new chat session."""
    session = ChatSession(id=session_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: Session = Depends(get_db)):
    """Delete a session and all its messages."""
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.query(ChatSession).filter(ChatSession.id == session_id).delete()
    db.commit()
    return {"message": "Session deleted"}


@router.post("")
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    """Chat endpoint with SSE streaming. Sends thinking, tool calls, and answer tokens."""
    session_id = request.session_id
    user_message = request.message

    # Ensure session exists
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        session = ChatSession(id=session_id, title="New Chat")
        db.add(session)
        db.commit()
        db.refresh(session)

    # If first message, update title
    msg_count = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).count()
    if msg_count == 0:
        # Simple title generator: first 30 chars
        title = user_message[:30] + "..." if len(user_message) > 30 else user_message
        session.title = title

    # Update session time
    session.updated_at = datetime.utcnow()
    db.commit()

    # Save user message
    db_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=user_message,
    )
    db.add(db_msg)
    db.commit()

    # Load conversation history
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .limit(40)
        .all()
    )

    messages = []
    for msg in history:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.content))

    previous_history = history[:-1] if history and history[-1].role == "user" and history[-1].content == user_message else history
    has_project_context = _history_has_project_context(previous_history)
    is_project_scoped = _is_project_scoped_query(user_message) or (
        _should_treat_as_scoped_with_history(user_message, has_project_context)
    )
    grounded_response = ""
    grounded_tool_log: list[dict] = []
    if _should_use_grounded_response(user_message):
        grounded_response, grounded_tool_log = _build_grounded_factual_response(user_message, db)

    async def event_stream():
        yield sse_event("thought", {"content": "Analyzing your question..."})

        combined_content = ""
        tool_calls_log = []

        try:
            if grounded_response:
                combined_content = grounded_response
                tool_calls_log.extend(grounded_tool_log)

                db_resp = ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=combined_content,
                    tool_calls=json.dumps(tool_calls_log),
                )
                db.add(db_resp)
                db.commit()

                yield sse_event("tool_call", {
                    "tool": grounded_tool_log[0]["tool"],
                    "message": "Using live workspace inventory lookup...",
                    "input": grounded_tool_log[0]["input"],
                })
                yield sse_event("tool_result", {
                    "tool": grounded_tool_log[0]["tool"],
                    "result": grounded_tool_log[0]["result"],
                })
                yield sse_event("answer", {"content": combined_content})
                yield sse_event("done", {})
                return

            async for event in chat_agent.astream_events({"messages": messages}, version="v2"):
                kind = event["event"]

                if kind == "on_tool_start":
                    # A tool is being called — stream to UI
                    tool_name = event["name"]
                    tool_input = event["data"].get("input", {})
                    tool_calls_log.append({"tool": tool_name, "input": tool_input})
                    yield sse_event("tool_call", {
                        "tool": tool_name,
                        "message": f"Using {tool_name}...",
                        "input": tool_input,
                    })

                elif kind == "on_tool_end":
                    # Tool finished — stream result to UI
                    tool_name = event["name"]
                    tool_output = event["data"].get("output", "")
                    clean_output = str(tool_output)
                    if hasattr(tool_output, "content"):
                        clean_output = str(tool_output.content)

                    for previous_call in reversed(tool_calls_log):
                        if previous_call.get("tool") == tool_name and "result" not in previous_call:
                            previous_call["result"] = clean_output
                            break
                    yield sse_event("tool_result", {
                        "tool": tool_name,
                        "result": clean_output,
                    })

                elif kind == "on_chat_model_stream":
                    # LLM is generating tokens (reasoning / thinking)
                    content = event["data"]["chunk"].content
                    if content and isinstance(content, str):
                        yield sse_event("thought", {"content": content})

                elif kind == "on_chain_end" and event["name"] == "LangGraph":
                    # Graph finished — extract final answer
                    final_state = event["data"]["output"]
                    final_messages = final_state.get("messages", [])
                    if final_messages:
                        last_msg = final_messages[-1]
                        if hasattr(last_msg, "content"):
                            combined_content = (
                                last_msg.content
                                if isinstance(last_msg.content, str)
                                else str(last_msg.content)
                            )

            # Persist assistant response
            db_resp = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=combined_content,
                tool_calls=json.dumps(tool_calls_log) if tool_calls_log else None,
            )
            db.add(db_resp)
            db.commit()

            yield sse_event("answer", {"content": combined_content})
            yield sse_event("done", {})

        except Exception as e:
            logger.error(f"Chat agent error: {traceback.format_exc()}")
            yield sse_event("error", {"message": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/history/{session_id}")
async def get_chat_history(session_id: str, db: Session = Depends(get_db)):
    """Get chat history for a session."""
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    return [ChatMessageResponse.model_validate(m) for m in messages]


@router.delete("/history/{session_id}")
async def clear_chat_history(session_id: str, db: Session = Depends(get_db)):
    """Clear chat history for a session."""
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.commit()
    return {"message": "Chat history cleared"}

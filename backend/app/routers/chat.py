"""Chat router with streaming responses from the chat agent."""
import asyncio
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
from app.tools.db_tools import (
    get_match_results,
    get_resume_inventory,
    get_tender_inventory,
    query_resumes_dynamic,
    sql_query_resumes,
)
from app.tools.search_tools import search_resumes, search_tenders
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
    "baki", "baaki", "rest", "remaining", "next",
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

DEFAULT_RESULT_PAGE_SIZE = 5
MORE_RESULTS_PATTERNS = (
    "show more",
    "more results",
    "more resumes",
    "more tenders",
    "next results",
    "next 5",
    "next five",
    "aur dikhao",
    "thoda aur",
    "aur batao",
)
REMAINING_RESULTS_PATTERNS = (
    "show rest",
    "show remaining",
    "remaining results",
    "remaining resumes",
    "remaining tenders",
    "all remaining",
    "rest results",
    "rest resumes",
    "rest tenders",
    "all of them",
    "baaki",
    "baki",
    "rest",
    "remaining",
    "sab dikhao",
    "sabhi",
)
AFFIRMATIVE_RESULTS_PATTERNS = (
    "yes",
    "yes please",
    "haan",
    "haan ji",
    "ha ji",
    "hanji",
    "ok",
    "okay",
    "sure",
    "continue",
    "go ahead",
    "go on",
)
TOOL_PAGINATION_TOTAL_PATTERN = re.compile(r"Total matching (?P<label>.+?): (?P<total>\d+)", re.IGNORECASE)
TOOL_PAGINATION_SHOWING_PATTERN = re.compile(
    r"Showing(?: remaining)? (?P<returned>\d+) of (?P<total>\d+) result\(s\) \((?P<start>\d+)-(?P<end>\d+)\)\.",
    re.IGNORECASE,
)
TOOL_PAGINATION_ZERO_PATTERN = re.compile(r"Showing 0 of (?P<total>\d+) result\(s\)\.", re.IGNORECASE)

PAGINATED_TOOL_REGISTRY = {
    tool.name: tool
    for tool in (
        sql_query_resumes,
        query_resumes_dynamic,
        get_match_results,
        get_resume_inventory,
        get_tender_inventory,
        search_resumes,
        search_tenders,
    )
}
RESUME_RESULT_TOOLS = {
    "sql_query_resumes",
    "query_resumes_dynamic",
    "get_match_results",
    "get_resume_inventory",
    "search_resumes",
}
TENDER_RESULT_TOOLS = {
    "get_tender_inventory",
    "search_tenders",
}
RICH_RESUME_FOLLOWUP_TOOLS = {
    "sql_query_resumes",
    "query_resumes_dynamic",
    "search_resumes",
    "get_resume_inventory",
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


def _resume_photo_url(resume: Resume) -> str | None:
    if not resume.photo_filename:
        return None
    return f"/api/resumes/photo/{resume.photo_filename}"


def _resume_profile_url(resume: Resume) -> str:
    return f"/resumes/{resume.id}"


def _extract_resume_ids_from_text(text: str) -> list[int]:
    resume_ids: list[int] = []
    seen: set[int] = set()
    patterns = (
        re.compile(r"\(ID:\s*(\d+)\)", re.IGNORECASE),
        re.compile(r"^\s*-\s*ID\s+(\d+):", re.IGNORECASE),
    )

    for line in (text or "").splitlines():
        for pattern in patterns:
            match = pattern.search(line)
            if not match:
                continue
            resume_id = int(match.group(1))
            if resume_id not in seen:
                seen.add(resume_id)
                resume_ids.append(resume_id)
            break
    return resume_ids


def _load_resumes_in_order(resume_ids: list[int], db: Session) -> list[Resume]:
    if not resume_ids:
        return []

    resumes = db.query(Resume).filter(Resume.id.in_(resume_ids)).all()
    resumes_by_id = {resume.id: resume for resume in resumes}
    return [resumes_by_id[resume_id] for resume_id in resume_ids if resume_id in resumes_by_id]


def _extract_followup_intro_from_content(content: str) -> str | None:
    for raw_line in (content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("**"):
            break
        if line.lower().startswith(("there are ", "showing ", "total matching ")):
            continue
        if line.endswith(":") and not line.startswith("-"):
            return line
    return None


def _derive_resume_followup_intro(
    history: list[ChatMessage],
    *,
    remaining_mode: bool,
) -> str:
    fallback = "Here are the remaining candidates:" if remaining_mode else "Here are the next candidates:"

    last_assistant_message = next((msg for msg in reversed(history) if msg.role == "assistant" and msg.content), None)
    if not last_assistant_message:
        return fallback

    intro = _extract_followup_intro_from_content(last_assistant_message.content)
    if not intro:
        return fallback

    if not intro.lower().startswith("here are"):
        return fallback

    descriptor = "remaining" if remaining_mode else "next"
    if re.search(r"\b(?:next|remaining)\s+candidates?\b", intro, re.IGNORECASE):
        updated = re.sub(
            r"\b(?:next|remaining)\s+candidates?\b",
            f"{descriptor} candidates",
            intro,
            count=1,
            flags=re.IGNORECASE,
        )
        return updated if updated.endswith(":") else f"{updated}:"

    if re.search(r"\bcandidates?\b", intro, re.IGNORECASE):
        updated = re.sub(r"\bcandidates?\b", f"{descriptor} candidates", intro, count=1, flags=re.IGNORECASE)
        return updated if updated.endswith(":") else f"{updated}:"

    return fallback


def _build_resume_followup_answer(
    resumes: list[Resume],
    *,
    intro: str,
    remaining_count: int,
) -> str:
    lines = [intro]

    for resume in resumes:
        try:
            skills = json.loads(resume.skills) if resume.skills else []
        except json.JSONDecodeError:
            logger.warning("Invalid skills JSON for resume_id=%s", resume.id)
            skills = []

        try:
            education = json.loads(resume.education) if resume.education else []
        except json.JSONDecodeError:
            logger.warning("Invalid education JSON for resume_id=%s", resume.id)
            education = []

        lines.extend([
            "",
            f"**{resume.name}** (ID: {resume.id})",
            f"- Role: {_format_resume_role(resume)}",
            f"- Experience: {(resume.total_years_experience or 0):g} years",
        ])

        photo_url = _resume_photo_url(resume)
        if photo_url:
            lines.append(f"- Photo URL: {photo_url}")
        lines.append(f"- Profile URL: {_resume_profile_url(resume)}")

        if education:
            lines.append("- Education:")
            lines.extend(f"  - {item}" for item in education)
        else:
            lines.append("- Education: N/A")

        lines.append(f"- Skills: {', '.join(skills[:12]) if skills else 'N/A'}")

    if remaining_count > 0:
        lines.extend([
            "",
            f"There are {remaining_count} more candidates available. Ask for \"show more\" to continue or \"show remaining\" to see everything left.",
        ])

    return "\n".join(lines).strip()


def _paginate_items(items: list, offset: int = 0, limit: int = DEFAULT_RESULT_PAGE_SIZE) -> tuple[list, int, int, int, int]:
    total = len(items)
    safe_offset = max(0, min(offset, total))
    safe_limit = max(0, limit)
    page = items[safe_offset:safe_offset + safe_limit]
    returned = len(page)
    start_index = safe_offset + 1 if returned else 0
    end_index = safe_offset + returned if returned else 0
    remaining = max(0, total - end_index)
    return page, total, start_index, end_index, remaining


def _format_pagination_summary(
    total: int,
    start_index: int,
    end_index: int,
    *,
    remaining_mode: bool = False,
) -> str:
    shown_count = max(0, end_index - start_index + 1) if start_index and end_index else 0
    prefix = "Showing remaining" if remaining_mode and shown_count else "Showing"
    if total == 0 or shown_count == 0:
        return f"{prefix} 0 of {total} result(s)."
    return f"{prefix} {shown_count} of {total} result(s) ({start_index}-{end_index})."


def _append_remaining_hint(lines: list[str], remaining: int) -> None:
    if remaining <= 0:
        return
    lines.append(
        f"{remaining} more result(s) are available. Ask for \"show more\" to see the next "
        f"{DEFAULT_RESULT_PAGE_SIZE}, or \"show remaining\" to see everything left."
    )


def _build_pagination_tool_log(
    *,
    tool_name: str,
    input_data: dict,
    result_message: str,
    kind: str,
    total: int,
    offset: int,
    limit: int,
    returned: int,
    context: dict | None = None,
) -> list[dict]:
    shown_until = offset + returned
    pagination = {
        "kind": kind,
        "offset": offset,
        "limit": limit,
        "returned": returned,
        "shown_until": shown_until,
        "total": total,
        "remaining": max(0, total - shown_until),
    }
    if context:
        pagination["context"] = context
    return [{
        "tool": tool_name,
        "input": input_data,
        "result": result_message,
        "pagination": pagination,
    }]


def _is_paginated_results_followup(message: str) -> bool:
    normalized = _normalize_query_text(message)
    if not normalized:
        return False

    return any(pattern in normalized for pattern in (*MORE_RESULTS_PATTERNS, *REMAINING_RESULTS_PATTERNS))


def _wants_remaining_results(message: str) -> bool:
    normalized = _normalize_query_text(message)
    if not normalized:
        return False

    return any(pattern in normalized for pattern in REMAINING_RESULTS_PATTERNS)


def _is_affirmative_results_followup(message: str) -> bool:
    normalized = _normalize_query_text(message)
    if not normalized:
        return False
    return normalized in AFFIRMATIVE_RESULTS_PATTERNS


def _matches_entity_terms_for_tool(tool_name: str, message: str) -> bool:
    tokens = _query_tokens(message)
    has_resume_terms = _has_any_token(tokens, RESUME_TERMS)
    has_tender_terms = _has_any_token(tokens, TENDER_TERMS)

    if has_resume_terms and tool_name in TENDER_RESULT_TOOLS:
        return False
    if has_tender_terms and tool_name in RESUME_RESULT_TOOLS:
        return False
    return True


def _load_tool_input(tool_name: str, raw_input: object) -> dict:
    if isinstance(raw_input, dict):
        return dict(raw_input)
    if tool_name in {"search_resumes", "search_tenders", "query_resumes_dynamic"}:
        return {"query": str(raw_input or "")}
    return {}


def _parse_paginated_tool_output(tool_name: str, tool_input: dict, tool_output: str) -> dict | None:
    output = tool_output or ""
    total_match = TOOL_PAGINATION_TOTAL_PATTERN.search(output)
    showing_match = TOOL_PAGINATION_SHOWING_PATTERN.search(output)
    zero_match = TOOL_PAGINATION_ZERO_PATTERN.search(output)
    if not total_match and not showing_match and not zero_match:
        return None

    total = int((showing_match or total_match or zero_match).group("total"))
    if showing_match:
        returned = int(showing_match.group("returned"))
        start_index = int(showing_match.group("start"))
        end_index = int(showing_match.group("end"))
        shown_until = end_index
        offset = max(0, start_index - 1)
    else:
        returned = 0
        offset = int(tool_input.get("offset", 0) or 0)
        shown_until = offset

    limit = int(tool_input.get("limit", returned or DEFAULT_RESULT_PAGE_SIZE) or DEFAULT_RESULT_PAGE_SIZE)
    label = total_match.group("label") if total_match else ""
    return {
        "kind": f"tool:{tool_name}",
        "tool": tool_name,
        "label": label,
        "offset": offset,
        "limit": limit,
        "returned": returned,
        "shown_until": shown_until,
        "total": total,
        "remaining": max(0, total - shown_until),
    }


def _trim_tool_answer(tool_output: str) -> str:
    if "Generated SQL:" in tool_output and "Total matching " in tool_output:
        return tool_output[tool_output.index("Total matching "):].strip()
    if "Interpreted Query:" in tool_output and "Total matching " in tool_output:
        return tool_output[tool_output.index("Total matching "):].strip()
    return tool_output.strip()


def _load_tool_calls(message: ChatMessage) -> list[dict]:
    if not message.tool_calls:
        return []
    try:
        tool_calls = json.loads(message.tool_calls)
    except json.JSONDecodeError:
        logger.warning("Invalid tool_calls JSON for chat_message_id=%s", message.id)
        return []
    return tool_calls if isinstance(tool_calls, list) else []


def _get_latest_paginated_tool_call(history: list[ChatMessage]) -> dict | None:
    for msg in reversed(history):
        if msg.role != "assistant":
            continue
        for tool_call in reversed(_load_tool_calls(msg)):
            pagination = tool_call.get("pagination")
            if isinstance(pagination, dict):
                return tool_call
    return None


def _build_resume_inventory_page_response(
    db: Session,
    *,
    offset: int = 0,
    limit: int = DEFAULT_RESULT_PAGE_SIZE,
    remaining_mode: bool = False,
) -> tuple[str, list[dict]]:
    resumes = db.query(Resume).order_by(Resume.id.asc()).all()
    page, total, start_index, end_index, remaining = _paginate_items(resumes, offset, limit)

    if total == 0:
        return "Current live resume inventory has 0 candidate(s).", _build_pagination_tool_log(
            tool_name="live_resume_inventory_lookup",
            input_data={"mode": "list", "offset": offset, "limit": limit},
            result_message="No resumes found in live inventory.",
            kind="resume_inventory",
            total=0,
            offset=offset,
            limit=limit,
            returned=0,
        )

    lines = [
        f"Current live resume inventory has {total} candidate(s).",
        _format_pagination_summary(total, start_index, end_index, remaining_mode=remaining_mode),
    ]
    lines.extend(_format_resume_list_item(resume) for resume in page)
    _append_remaining_hint(lines, remaining)

    returned = len(page)
    return "\n".join(lines), _build_pagination_tool_log(
        tool_name="live_resume_inventory_lookup",
        input_data={"mode": "list", "offset": offset, "limit": limit},
        result_message=f"Fetched {returned} of {total} resume(s) from live inventory.",
        kind="resume_inventory",
        total=total,
        offset=offset,
        limit=limit,
        returned=returned,
    )


def _build_tender_inventory_page_response(
    db: Session,
    *,
    offset: int = 0,
    limit: int = DEFAULT_RESULT_PAGE_SIZE,
    remaining_mode: bool = False,
) -> tuple[str, list[dict]]:
    tenders = db.query(Tender).order_by(Tender.id.asc()).all()
    page, total, start_index, end_index, remaining = _paginate_items(tenders, offset, limit)

    if total == 0:
        return "Current live tender inventory has 0 tender(s).", _build_pagination_tool_log(
            tool_name="live_tender_inventory_lookup",
            input_data={"mode": "list", "offset": offset, "limit": limit},
            result_message="No tenders found in live inventory.",
            kind="tender_inventory",
            total=0,
            offset=offset,
            limit=limit,
            returned=0,
        )

    lines = [
        f"Current live tender inventory has {total} tender(s).",
        _format_pagination_summary(total, start_index, end_index, remaining_mode=remaining_mode),
    ]
    lines.extend(_format_tender_list_item(tender) for tender in page)
    _append_remaining_hint(lines, remaining)

    returned = len(page)
    return "\n".join(lines), _build_pagination_tool_log(
        tool_name="live_tender_inventory_lookup",
        input_data={"mode": "list", "offset": offset, "limit": limit},
        result_message=f"Fetched {returned} of {total} tender(s) from live inventory.",
        kind="tender_inventory",
        total=total,
        offset=offset,
        limit=limit,
        returned=returned,
    )


def _build_name_prefix_page_response(
    prefix: str,
    db: Session,
    *,
    offset: int = 0,
    limit: int = DEFAULT_RESULT_PAGE_SIZE,
    remaining_mode: bool = False,
) -> tuple[str, list[dict]]:
    normalized_prefix = prefix.casefold()
    resumes = db.query(Resume).order_by(Resume.id.asc()).all()
    matches = [resume for resume in resumes if (resume.name or "").casefold().startswith(normalized_prefix)]

    prefix_label = prefix.upper() if len(prefix) == 1 else prefix
    total = len(matches)
    candidate_word = "candidate" if total == 1 else "candidates"
    name_phrase = "name starts" if total == 1 else "names start"
    prefix_kind = "letter" if len(prefix) == 1 else "prefix"

    if total == 0:
        response = (
            f"There are 0 {candidate_word} whose {name_phrase} with the {prefix_kind} "
            f"\"{prefix_label}\".\nNo candidate names in the current live inventory match that prefix."
        )
        return response, _build_pagination_tool_log(
            tool_name="live_resume_name_prefix_lookup",
            input_data={"prefix": prefix, "offset": offset, "limit": limit},
            result_message="No resume names matched the requested prefix.",
            kind="resume_name_prefix",
            total=0,
            offset=offset,
            limit=limit,
            returned=0,
            context={"prefix": prefix},
        )

    page, _, start_index, end_index, remaining = _paginate_items(matches, offset, limit)
    lines = [
        f"There {'is' if total == 1 else 'are'} {total} {candidate_word} whose {name_phrase} with the {prefix_kind} \"{prefix_label}\".",
        _format_pagination_summary(total, start_index, end_index, remaining_mode=remaining_mode),
    ]
    lines.extend(_format_resume_list_item(resume) for resume in page)
    _append_remaining_hint(lines, remaining)

    returned = len(page)
    return "\n".join(lines), _build_pagination_tool_log(
        tool_name="live_resume_name_prefix_lookup",
        input_data={"prefix": prefix, "offset": offset, "limit": limit},
        result_message=f"Matched {returned} of {total} resume(s) for prefix lookup.",
        kind="resume_name_prefix",
        total=total,
        offset=offset,
        limit=limit,
        returned=returned,
        context={"prefix": prefix},
    )


async def _build_tool_pagination_followup_response(
    message: str,
    paginated_tool_call: dict,
    history: list[ChatMessage],
    db: Session,
) -> tuple[str, list[dict]]:
    tool_name = paginated_tool_call.get("tool")
    if not isinstance(tool_name, str) or tool_name not in PAGINATED_TOOL_REGISTRY:
        return "", []
    if not _matches_entity_terms_for_tool(tool_name, message):
        return "", []

    pagination = paginated_tool_call.get("pagination") or {}
    total = int(pagination.get("total") or 0)
    shown_until = int(pagination.get("shown_until") or 0)
    if shown_until >= total:
        label = pagination.get("label") or "result(s)"
        return f"All {total} {label} are already shown.", []

    remaining_mode = _wants_remaining_results(message) or _is_affirmative_results_followup(message)
    next_input = _load_tool_input(tool_name, paginated_tool_call.get("input"))
    next_input["offset"] = shown_until
    next_input["limit"] = DEFAULT_RESULT_PAGE_SIZE

    tool_output = await asyncio.to_thread(PAGINATED_TOOL_REGISTRY[tool_name].invoke, next_input)
    clean_output = str(tool_output)
    pagination_data = _parse_paginated_tool_output(tool_name, next_input, clean_output)
    tool_log = [{
        "tool": tool_name,
        "input": next_input,
        "result": clean_output,
    }]
    if pagination_data:
        tool_log[0]["pagination"] = pagination_data

    if tool_name in RICH_RESUME_FOLLOWUP_TOOLS:
        resume_ids = _extract_resume_ids_from_text(clean_output)
        resumes = _load_resumes_in_order(resume_ids, db)
        if resumes:
            remaining_count = int((pagination_data or {}).get("remaining", 0))
            intro = _derive_resume_followup_intro(history, remaining_mode=remaining_mode)
            answer = _build_resume_followup_answer(
                resumes,
                intro=intro,
                remaining_count=remaining_count,
            )
            return answer, tool_log

    answer = _trim_tool_answer(clean_output)
    if remaining_mode:
        answer = f"Here are the remaining results:\n\n{answer}"
    else:
        answer = f"Here are the next results:\n\n{answer}"
    return answer, tool_log


async def _build_paginated_followup_response(
    message: str,
    history: list[ChatMessage],
    db: Session,
) -> tuple[str, list[dict]]:
    paginated_tool_call = _get_latest_paginated_tool_call(history)
    if not paginated_tool_call:
        return "", []

    if not (_is_paginated_results_followup(message) or _is_affirmative_results_followup(message)):
        return "", []

    pagination = paginated_tool_call.get("pagination") or {}
    kind = pagination.get("kind")

    total = int(pagination.get("total") or 0)
    shown_until = int(pagination.get("shown_until") or 0)
    if shown_until >= total:
        result_label = {
            "resume_inventory": "resume result(s)",
            "tender_inventory": "tender result(s)",
            "resume_name_prefix": "matching candidate(s)",
        }.get(kind, "result(s)")
        return f"All {total} {result_label} are already shown.", []

    offset = shown_until
    remaining_mode = _wants_remaining_results(message) or _is_affirmative_results_followup(message)
    limit = DEFAULT_RESULT_PAGE_SIZE

    if kind == "resume_inventory":
        resumes = db.query(Resume).order_by(Resume.id.asc()).all()
        page, _, _, _, remaining = _paginate_items(resumes, offset, limit)
        raw_response, tool_log = _build_resume_inventory_page_response(
            db,
            offset=offset,
            limit=limit,
            remaining_mode=remaining_mode,
        )
        if not page:
            return raw_response, tool_log

        if tool_log:
            tool_log[0]["result"] = raw_response
        answer = _build_resume_followup_answer(
            page,
            intro=_derive_resume_followup_intro(history, remaining_mode=remaining_mode),
            remaining_count=remaining,
        )
        return answer, tool_log

    if kind == "tender_inventory":
        return _build_tender_inventory_page_response(db, offset=offset, limit=limit, remaining_mode=remaining_mode)

    if kind == "resume_name_prefix":
        context = pagination.get("context") or {}
        prefix = context.get("prefix")
        if isinstance(prefix, str) and prefix:
            normalized_prefix = prefix.casefold()
            resumes = db.query(Resume).order_by(Resume.id.asc()).all()
            matches = [resume for resume in resumes if (resume.name or "").casefold().startswith(normalized_prefix)]
            page, _, _, _, remaining = _paginate_items(matches, offset, limit)
            raw_response, tool_log = _build_name_prefix_page_response(
                prefix,
                db,
                offset=offset,
                limit=limit,
                remaining_mode=remaining_mode,
            )
            if not page:
                return raw_response, tool_log

            if tool_log:
                tool_log[0]["result"] = raw_response
            answer = _build_resume_followup_answer(
                page,
                intro=_derive_resume_followup_intro(history, remaining_mode=remaining_mode),
                remaining_count=remaining,
            )
            return answer, tool_log

    if isinstance(kind, str) and kind.startswith("tool:"):
        return await _build_tool_pagination_followup_response(message, paginated_tool_call, history, db)

    return "", []


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
    return _build_name_prefix_page_response(prefix, db)


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
            return _build_resume_inventory_page_response(db)

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
            return _build_tender_inventory_page_response(db)

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
    pagination_followup_response, pagination_followup_log = await _build_paginated_followup_response(
        user_message,
        previous_history,
        db,
    )
    if pagination_followup_response:
        grounded_response = pagination_followup_response
        grounded_tool_log = pagination_followup_log
    elif _should_use_grounded_response(user_message):
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

                if grounded_tool_log:
                    display_tool = grounded_tool_log[0]["tool"]
                    display_message = (
                        "Using live workspace inventory lookup..."
                        if str(display_tool).startswith("live_")
                        else f"Continuing previous paginated results with {display_tool}..."
                    )
                    yield sse_event("tool_call", {
                        "tool": display_tool,
                        "message": display_message,
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
                            tool_input = _load_tool_input(tool_name, previous_call.get("input"))
                            pagination = _parse_paginated_tool_output(tool_name, tool_input, clean_output)
                            if pagination:
                                previous_call["pagination"] = pagination
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

"""Database lookup tools for the chat agent."""
import json
import logging
import re
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy import or_, text

from app.database import SessionLocal
from app.models import Resume, Tender, MatchResult, CommonSkill, CommonEducation
from langchain_core.messages import HumanMessage
from app.services.llm import get_reasoning_llm

logger = logging.getLogger(__name__)

EDUCATION_LEVEL_EQUIVALENTS = {
    "graduate": {"graduate", "undergraduate", "bachelor", "bachelors", "graduation", "degree"},
    "postgraduate": {"postgraduate", "post", "master", "masters", "pg", "postgraduation", "post_graduation"},
    "phd": {"phd", "doctorate", "doctoral", "doctor"},
    "diploma": {"diploma", "polytechnic"},
    "highschool": {"highschool", "school", "10th", "12th", "secondary", "senior_secondary", "intermediate"},
}

EDUCATION_LEVEL_SUPERSETS = {
    "graduate": {"graduate", "level_graduate_and_postgraduate"},
    "postgraduate": {"postgraduate", "level_graduate_and_postgraduate", "phd"},
    "phd": {"phd"},
    "diploma": {"diploma"},
    "highschool": {"highschool"},
}

EDUCATION_CANONICAL_TOKEN_MAP = {
    "btech": {"btech", "b tech", "b.tech", "bachelor_engineering", "bachelor of technology", "engineering"},
    "be": {"be", "b.e", "b e", "bachelor_engineering", "engineering"},
    "bachelor": {"bachelor", "bachelors", "graduate", "graduation", "degree"},
    "mtech": {"mtech", "m tech", "m.tech", "master_engineering", "master of technology", "engineering"},
    "me": {"me", "m.e", "m e", "master_engineering", "engineering"},
    "master": {"master", "masters", "postgraduate", "post graduation", "pg"},
    "phd": {"phd", "doctorate", "doctoral", "doctor of philosophy"},
    "mca": {"mca", "master of computer applications", "computer applications"},
    "bca": {"bca", "bachelor of computer applications", "computer applications"},
    "bsc": {"bsc", "b.sc", "b sc", "bachelor of science", "science"},
    "msc": {"msc", "m.sc", "m sc", "master of science", "science"},
    "amie": {"amie", "associate member of institution of engineers", "engineering"},
    "civil": {"civil", "civil engineering"},
    "structural": {"structural", "structural engineering"},
    "computer": {"computer", "computer science", "computer applications"},
    "geology": {"geology", "geological"},
    "environmental": {"environmental", "environment"},
}

EDUCATION_STOPWORDS = {
    "candidate", "candidates", "find", "show", "list", "all", "who", "with", "having", "resume",
    "resumes", "qualification", "qualifications", "degree", "degrees", "need", "looking", "for",
    "vs", "or", "and", "in", "of", "the", "please", "give", "me", "from", "done", "completed",
    "complete", "finished", "have", "has",
}

DOMAIN_HINT_TERMS = {
    "railway", "metro", "highway", "road", "bridge", "tunnel", "epc", "infrastructure",
    "construction", "civil", "telecom", "power", "it", "software", "gis", "drone",
    "survey", "design", "government", "psu", "nhai",
}


class CommonValueSelection(BaseModel):
    selected_common_values: list[str] = Field(default_factory=list)
    reasoning: str = ""


class ResumeQueryInterpretation(BaseModel):
    original_query: str
    experience_operator: Optional[str] = None
    experience_value: Optional[float] = None
    experience_upper_value: Optional[float] = None
    education_query: Optional[str] = None
    skill_queries: list[str] = Field(default_factory=list)
    excluded_skill_queries: list[str] = Field(default_factory=list)
    domain_query: Optional[str] = None
    intent_notes: list[str] = Field(default_factory=list)


def _unique_preserve(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _normalize_lookup_text(value: str) -> str:
    if not value:
        return ""
    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"\b(19|20)\d{2}\b", " ", normalized)
    normalized = re.sub(r"[_/\\-]+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9\s]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _normalized_contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = _normalize_lookup_text(text)
    normalized_phrase = _normalize_lookup_text(phrase)
    if not normalized_text or not normalized_phrase:
        return False
    return normalized_phrase in normalized_text


def _tokenize_lookup_text(value: str) -> list[str]:
    normalized = _normalize_lookup_text(value)
    if not normalized:
        return []
    return [token for token in normalized.split() if len(token) > 2]


def _chunk_text(value: str, chunk_size: int = 700, overlap: int = 120) -> list[str]:
    text_value = (value or "").strip()
    if not text_value:
        return []
    if len(text_value) <= chunk_size:
        return [text_value]

    chunks = []
    start = 0
    while start < len(text_value):
        end = min(len(text_value), start + chunk_size)
        chunk = text_value[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text_value):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _score_text_chunk(chunk: str, query_tokens: list[str], boost_terms: list[str]) -> int:
    haystack = _normalize_lookup_text(chunk)
    if not haystack:
        return 0

    score = 0
    for token in query_tokens:
        if token in haystack:
            score += 3
    for term in boost_terms:
        if term in haystack:
            score += 2
    return score


def _extract_search_phrases(category: str, value: str) -> list[str]:
    if not value:
        return []

    normalized = value.replace("_", " ")
    phrases = [normalized]
    if category == "education":
        # Split on common delimiters and conjunctions
        base_parts = re.split(r"[,;|\n]|\bvs\b|\band\b|\bor\b", normalized, flags=re.IGNORECASE)
        for part in base_parts:
            part = part.strip()
            if part:
                phrases.append(part)
        
        lower_value = normalized.lower()
        for marker in (" from ", " at ", " university ", " college ", " institute ", " school "):
            index = lower_value.find(marker)
            if index > 0:
                phrases.append(normalized[:index].strip())

    cleaned = []
    for phrase in phrases:
        candidate = _normalize_lookup_text(phrase)
        if candidate and candidate not in cleaned:
            cleaned.append(candidate)
    return cleaned


def _contains_normalized_marker(normalized_text: str, marker: str) -> bool:
    marker_normalized = _normalize_lookup_text(marker)
    if not marker_normalized:
        return False

    text_tokens = set(normalized_text.split())
    marker_tokens = marker_normalized.split()
    if len(marker_tokens) == 1 and marker_tokens[0] in text_tokens:
        return True
    if len(marker_tokens) > 1 and marker_normalized in normalized_text:
        return True

    if len(marker_normalized) <= 2 or all(len(token) == 1 for token in marker_tokens):
        return False
    compact_text = normalized_text.replace(" ", "")
    compact_marker = marker_normalized.replace(" ", "")
    return bool(compact_marker) and compact_marker in compact_text


def _education_semantic_terms(user_query: str) -> set[str]:
    raw_query = user_query or ""
    normalized = _normalize_lookup_text(user_query)
    terms = set(_tokenize_lookup_text(user_query))
    phrase_checks = [
        (r"\bb\.?\s*tech\b|\bbachelor of technology\b", "btech"),
        (r"\bbachelor of engineering\b", "be"),
        (r"\bm\.?\s*tech\b|\bmaster of technology\b", "mtech"),
        (r"\bmaster of engineering\b", "me"),
        (r"\bb\.?\s*c\.?\s*a\b|\bbachelor of computer applications\b", "bca"),
        (r"\bm\.?\s*c\.?\s*a\b|\bmaster of computer applications\b", "mca"),
        (r"\bb\.?\s*sc\b|\bb\.?\s*s\.?\s*c\b|\bbachelor of science\b", "bsc"),
        (r"\bm\.?\s*sc\b|\bm\.?\s*s\.?\s*c\b|\bmaster of science\b", "msc"),
        (r"\bamie\b|\bassociate member of institution of engineers\b", "amie"),
        (r"\bph\.?\s*d\b|\bdoctorate\b|\bdoctoral\b|\bdoctor of philosophy\b", "phd"),
    ]

    for pattern, key in phrase_checks:
        if re.search(pattern, raw_query, re.IGNORECASE):
            terms.update(EDUCATION_CANONICAL_TOKEN_MAP[key])

    be_context_pattern = r"\bb\.?\s*e(?:\.|\b)(?=(?:\s+(?:in\s+)?)?(?:civil|mechanical|electrical|electronics|computer|chemical|structural|engineering)\b|[,\-/]|$)"
    me_context_pattern = r"\bm\.?\s*e(?:\.|\b)(?=(?:\s+(?:in\s+)?)?(?:civil|mechanical|electrical|electronics|computer|chemical|structural|engineering)\b|[,\-/]|$)"
    if re.search(be_context_pattern, raw_query, re.IGNORECASE):
        terms.update(EDUCATION_CANONICAL_TOKEN_MAP["be"])
    if re.search(me_context_pattern, raw_query, re.IGNORECASE):
        terms.update(EDUCATION_CANONICAL_TOKEN_MAP["me"])

    if "eng" in terms or "engg" in terms:
        terms.update({"engineering"})

    if "post graduation" in normalized or "post graduate" in normalized:
        terms.update({"postgraduation", "postgraduate", "master", "masters", "pg"})
    if "under graduate" in normalized or "undergraduate" in normalized:
        terms.update({"graduate", "bachelor", "bachelors"})

    return {term for term in terms if term}


def _extract_subject_terms_from_semantics(semantic_terms: set[str]) -> set[str]:
    subject_terms = set()
    level_terms = set().union(*EDUCATION_LEVEL_EQUIVALENTS.values())
    for term in semantic_terms:
        if term in EDUCATION_STOPWORDS or term in level_terms:
            continue
        if term in {"engineering", "science", "computer", "applications"}:
            subject_terms.add(term)
            continue
        if len(term) > 2:
            subject_terms.add(term)
    return subject_terms


def _is_meaningful_education_item(item: dict) -> bool:
    item_level = (item.get("level") or "other").lower()
    combined = _normalize_lookup_text(" ".join([
        item.get("name", ""),
        item.get("display_label", ""),
        *item.get("aliases", []),
    ]))
    if not combined:
        return False

    quality_markers = {
        "bachelor", "master", "phd", "doctorate", "diploma", "amie", "mca", "bca",
        "bsc", "msc", "btech", "mtech", "secondary", "10th", "12th",
    }
    if not any(marker in combined for marker in quality_markers):
        return False

    return item_level in {"graduate", "postgraduate", "phd", "diploma", "highschool", "level_graduate_and_postgraduate", "other"}


def _education_query_constraints(user_query: str) -> dict:
    """Infer normalized education constraints from a free-form query."""
    normalized = _normalize_lookup_text(user_query)
    semantic_terms = _education_semantic_terms(user_query)
    levels = set()
    if "post graduation" in normalized or "post graduate" in normalized or "postgraduation" in normalized:
        levels.add("postgraduate")
    else:
        levels = {
            level
            for level, synonyms in EDUCATION_LEVEL_EQUIVALENTS.items()
            if semantic_terms & synonyms
        }
    has_subject_constraint = any(
        token not in EDUCATION_STOPWORDS and
        all(token not in synonyms for synonyms in EDUCATION_LEVEL_EQUIVALENTS.values())
        for token in semantic_terms
    )
    return {
        "normalized": normalized,
        "semantic_terms": semantic_terms,
        "levels": levels,
        "subject_terms": _extract_subject_terms_from_semantics(semantic_terms),
        "has_subject_constraint": has_subject_constraint,
    }


def _item_matches_education_constraints(item: dict, constraints: dict) -> bool:
    """Check if a catalog education entry matches the inferred user constraints."""
    if not _is_meaningful_education_item(item):
        return False

    levels = constraints.get("levels", set())
    if levels:
        item_level = (item.get("level") or "other").lower()
        if not any(item_level in EDUCATION_LEVEL_SUPERSETS.get(level, {level}) for level in levels):
            return False

    subject_terms = constraints.get("subject_terms", set())
    if not subject_terms:
        return True

    item_semantics = _education_semantic_terms(" ".join([
        item.get("name", ""),
        item.get("display_label", ""),
        *item.get("aliases", []),
        *item.get("search_terms", []),
    ]))
    specific_subject_terms = subject_terms - {"engineering", "science", "computer", "applications"}
    if specific_subject_terms:
        return bool(specific_subject_terms & item_semantics)
    return bool(subject_terms & item_semantics)


def _build_search_terms(category: str, name: str, aliases: list[str]) -> list[str]:
    search_terms = []
    for candidate in [name, *aliases]:
        for phrase in _extract_search_phrases(category, candidate):
            if phrase not in search_terms:
                search_terms.append(phrase)
    return search_terms


def _catalog_exact_matches(category: str, user_query: str, items: list[dict]) -> list[str]:
    """Prefer exact catalog phrase matches over broad semantic expansion when available."""
    query_phrases = set(_extract_search_phrases(category, user_query))
    if not query_phrases:
        return []

    exact_matches = []
    for item in items:
        item_phrases = set()
        for candidate in [item["name"], item.get("display_label", ""), *item.get("aliases", [])]:
            item_phrases.update(_extract_search_phrases(category, candidate))

        if query_phrases & item_phrases:
            exact_matches.append(item["name"])

    return _unique_preserve(exact_matches)


def _best_display_label(name: str, aliases: list[str], search_terms: list[str]) -> str:
    for candidate in [*aliases, *search_terms, name]:
        if not candidate:
            continue
        cleaned = candidate.replace("_", " ").strip()
        if cleaned:
            return cleaned
    return name


def _load_common_items(db, category: str) -> list[dict]:
    model = CommonSkill if category == "skills" else CommonEducation
    items = db.query(model).all()
    loaded = []
    for item in items:
        aliases = json.loads(item.aliases) if item.aliases else []
        search_terms = _build_search_terms(category, item.name, aliases)
        entry = {
            "name": item.name,
            "aliases": aliases,
            "search_terms": search_terms,
            "concepts": search_terms,
            "display_label": _best_display_label(item.name, aliases, search_terms),
        }
        if hasattr(item, "level"):
            entry["level"] = item.level or "other"
        loaded.append(entry)
    return loaded


def _fallback_resolve_common_values(category: str, user_query: str, items: list[dict]) -> list[str]:
    query = _normalize_lookup_text(user_query)
    query_tokens = set(query.split())
    if not query_tokens:
        return []

    matched = []
    for item in items:
        # We check name and aliases for the fallback
        candidates = [item["name"], item.get("display_label", ""), *item["aliases"]]
        item_text = " ".join(_normalize_lookup_text(c) for c in candidates if c)
        item_tokens = set(item_text.split())

        if not item_tokens: continue

        # Stricter token overlap: Require at least one specific match or high Jaccard
        intersection = query_tokens & item_tokens
        if not intersection: continue

        # If it's education, ignore generic "bachelor" / "master" matches unless they have the subject
        if category == "education":
            is_pure_science_query = "science" in query_tokens and "engineering" not in query_tokens
            is_engineering_query = "engineering" in query_tokens or "btech" in query_tokens or "b.t" in query
            
            if is_pure_science_query and "engineering" in item_tokens and "science" not in item_tokens:
                continue # Skip engineering if user asked for pure science
            if is_engineering_query and "science" in item_tokens and "engineering" not in item_tokens:
                continue # Skip science if user asked for engineering

        overlap = len(intersection) / len(query_tokens)
        threshold = 0.3 if category == "education" else 0.5
        if overlap >= threshold: # Lower threshold for education to handle "PhD vs Master" type noise
            matched.append((overlap, item["name"]))

    matched.sort(key=lambda x: (-x[0], x[1]))
    return [name for _, name in matched[:10]]


def _resolve_common_values(category: str, user_query: str, items: list[dict]) -> list[str]:
    logger.info("Resolving common values for %s with query: '%s'", category, user_query)
    if not user_query.strip() or not items:
        return []

    filtered_items = items
    if category == "education":
        filtered_items = [item for item in items if _is_meaningful_education_item(item)]
        exact_matches = _catalog_exact_matches(category, user_query, filtered_items)
        if exact_matches:
            return exact_matches

        constraints = _education_query_constraints(user_query)
        scored_matches = []
        for item in filtered_items:
            if not _item_matches_education_constraints(item, constraints):
                continue

            item_text = " ".join([
                item.get("name", ""),
                item.get("display_label", ""),
                *item.get("aliases", []),
                *item.get("search_terms", []),
            ])
            item_semantics = _education_semantic_terms(item_text)
            score = 0

            for level in constraints["levels"]:
                if (item.get("level") or "other").lower() in EDUCATION_LEVEL_SUPERSETS.get(level, {level}):
                    score += 5

            subject_overlap = constraints["subject_terms"] & item_semantics
            score += len(subject_overlap) * 3

            if constraints["normalized"] and constraints["normalized"] in _normalize_lookup_text(item_text):
                score += 4

            exact_term_overlap = constraints["semantic_terms"] & item_semantics
            score += min(len(exact_term_overlap), 4)

            scored_matches.append((score, item["name"]))

        scored_matches.sort(key=lambda pair: (-pair[0], pair[1]))
        selected = _unique_preserve([name for score, name in scored_matches if score > 0])
        if selected:
            return selected[:50]

    selected = _fallback_resolve_common_values(category, user_query, filtered_items)
    return selected


def _education_raw_query_patterns(user_query: str) -> list[str]:
    normalized = _normalize_lookup_text(user_query)
    constraints = _education_query_constraints(user_query)
    semantic_terms = constraints.get("semantic_terms", set())
    patterns = []

    def add(*values: str):
        for value in values:
            cleaned = value.strip().lower()
            if cleaned and cleaned not in patterns:
                patterns.append(cleaned)

    if normalized:
        add(user_query, normalized, normalized.replace(" ", "."))

    for subject in semantic_terms:
        if subject not in {"graduate", "postgraduate", "engineering"}:
            add(subject.replace("_", " "))

    if {"btech", "b tech", "b.tech", "bachelor of technology"} & semantic_terms:
        add("b.tech", "b tech", "bachelor of technology")
    if {"mtech", "m tech", "m.tech", "master of technology"} & semantic_terms:
        add("m.tech", "m tech", "master of technology")
    if {"graduate", "bachelor", "bachelors", "graduation"} & semantic_terms:
        add("graduate", "bachelor", "bachelors", "graduation")
    if {"master", "masters", "postgraduate", "postgraduation"} & semantic_terms:
        add("master", "masters", "post graduation", "postgraduate")

    return patterns


def _infer_education_level_from_terms(item_terms: set[str]) -> str:
    """Prioritize more advanced degrees over lower ones."""
    if "phd" in item_terms or "doctorate" in item_terms:
        return "phd"
    if {"postgraduate", "master", "master_engineering", "mtech", "msc", "mca"} & item_terms:
        return "postgraduate"
    if {"graduate", "bachelor", "bachelor_engineering", "btech", "bsc", "bca", "amie", "be"} & item_terms:
        return "graduate"
    if "diploma" in item_terms:
        return "diploma"
    if "highschool" in item_terms:
        return "highschool"
    return "other"


def _education_entry_matches_query(entry: str, user_query: str) -> bool:
    """Robust fallback for resumes with messy raw data bypassing standardization."""
    normalized_entry = _normalize_lookup_text(entry)
    if not normalized_entry:
        return False

    entry_terms = _education_semantic_terms(entry)
    constraints = _education_query_constraints(user_query)

    if constraints["levels"]:
        inferred_level = _infer_education_level_from_terms(entry_terms)
        if not any(inferred_level in EDUCATION_LEVEL_SUPERSETS.get(level, {level}) for level in constraints["levels"]):
            return False

    subject_terms = constraints["subject_terms"]
    if subject_terms and not (subject_terms & entry_terms):
        return False

    return True


def _resume_matches_education_query(resume: Resume, user_query: str, resolved_education: list[str]) -> bool:
    standardized_education = json.loads(resume.standardized_education) if resume.standardized_education else []
    if any(value in standardized_education for value in resolved_education):
        return True

    raw_education_entries = json.loads(resume.education) if resume.education else []
    if not raw_education_entries:
        return False

    return any(_education_entry_matches_query(entry, user_query) for entry in raw_education_entries)


def _resume_skill_phrases(resume: Resume) -> list[str]:
    raw_skills = json.loads(resume.skills) if resume.skills else []
    standardized_skills = json.loads(resume.standardized_skills) if resume.standardized_skills else []
    parsed = json.loads(resume.parsed_data) if resume.parsed_data else {}
    domain_expertise = json.loads(resume.domain_expertise) if resume.domain_expertise else []
    phrases = [*raw_skills, *standardized_skills, *domain_expertise]
    phrases.extend(parsed.get("skills", []))
    return [str(value) for value in phrases if value]


def _resume_domain_phrases(resume: Resume) -> list[str]:
    phrases = json.loads(resume.domain_expertise) if resume.domain_expertise else []
    parsed = json.loads(resume.parsed_data) if resume.parsed_data else {}
    phrases.extend(parsed.get("domain_expertise", []))
    experience = parsed.get("experience", [])
    for item in experience:
        if not isinstance(item, dict):
            continue
        for key in ("sector", "subsector", "role", "description"):
            if item.get(key):
                phrases.append(str(item[key]))
    return [str(value) for value in phrases if value]


def _resume_matches_skill_query(resume: Resume, skill_query: str, skill_items: list[dict]) -> bool:
    resolved_skills = _resolve_common_values("skills", skill_query, skill_items)
    phrases = _resume_skill_phrases(resume)
    normalized_skill_query = _normalize_lookup_text(skill_query)

    for phrase in phrases:
        if _normalized_contains_phrase(phrase, normalized_skill_query):
            return True

    standardized_skills = json.loads(resume.standardized_skills) if resume.standardized_skills else []
    if resolved_skills and any(skill in standardized_skills for skill in resolved_skills):
        return True

    query_tokens = set(_tokenize_lookup_text(skill_query))
    if not query_tokens:
        return False
    return any(query_tokens <= set(_tokenize_lookup_text(phrase)) for phrase in phrases)


def _resume_matches_domain_phrase(resume: Resume, domain_query: str) -> bool:
    extracted_domain = _extract_domain_phrase(domain_query)
    if extracted_domain:
        domain_query = extracted_domain
    phrases = _resume_domain_phrases(resume)
    normalized_query = _normalize_lookup_text(domain_query)
    query_tokens = set(_tokenize_lookup_text(domain_query))

    if len(normalized_query.replace(" ", "")) <= 2:
        compact_query = normalized_query.replace(" ", "")
        return any(
            compact_query in {token.replace(" ", "") for token in _tokenize_lookup_text(phrase)} or
            compact_query in {
                token.replace(" ", "")
                for token in _normalize_lookup_text(phrase).split()
            }
            for phrase in phrases
        )

    if any(_normalized_contains_phrase(phrase, normalized_query) for phrase in phrases):
        return True
    return any(query_tokens <= set(_tokenize_lookup_text(phrase)) for phrase in phrases if query_tokens)


def _extract_experience_filter(user_query: str) -> tuple[Optional[str], Optional[float], Optional[float]]:
    normalized = _normalize_lookup_text(user_query)

    between_match = re.search(
        r"(?:between|from)\s+(\d+(?:\.\d+)?)\s+(?:and|to)\s+(\d+(?:\.\d+)?)\s+(?:years?|yrs?)",
        normalized,
    )
    if between_match:
        return "between", float(between_match.group(1)), float(between_match.group(2))

    experience_patterns = [
        ("gt", r"(?:more than|greater than|over|above)\s+(\d+(?:\.\d+)?)\s+(?:years?|yrs?)"),
        ("gte", r"(?:at least|minimum of|min(?:imum)?|not less than)\s+(\d+(?:\.\d+)?)\s+(?:years?|yrs?)"),
        ("lte", r"(?:at most|up to|no more than|not more than)\s+(\d+(?:\.\d+)?)\s+(?:years?|yrs?)"),
        ("lt", r"(?:less than|under|below)\s+(\d+(?:\.\d+)?)\s+(?:years?|yrs?)"),
        ("eq", r"(?:exactly)\s+(\d+(?:\.\d+)?)\s+(?:years?|yrs?)"),
        ("gte", r"(\d+(?:\.\d+)?)\s*\+\s*(?:years?|yrs?)"),
    ]
    for operator, pattern in experience_patterns:
        match = re.search(pattern, normalized)
        if match:
            return operator, float(match.group(1)), None

    trailing_match = re.search(r"(\d+(?:\.\d+)?)\s+(?:years?|yrs?)\s+experience", normalized)
    if trailing_match:
        return "eq", float(trailing_match.group(1)), None
    return None, None, None


def _extract_education_phrase(user_query: str) -> Optional[str]:
    raw_query = " ".join(user_query.split())
    lowered = raw_query.lower()

    if any(marker in lowered for marker in ["postgraduation", "post graduation", "postgraduate", "master", "masters", "pg"]):
        return "postgraduation"
    if any(marker in lowered for marker in ["graduation", "graduate", "undergraduate", "bachelor", "bachelors"]):
        return "graduation"

    patterns = [
        r"(?:with|having|has)\s+([\w\s./&+-]+?)\s+background",
        r"([\w\s./&+-]+?)\s+background",
        r"background\s+in\s+([\w\s./&+-]+)",
        r"education\s+in\s+([\w\s./&+-]+)",
        r"([\w\s./&+-]+?)\s+education",
        r"qualification\s+in\s+([\w\s./&+-]+)",
        r"degree\s+in\s+([\w\s./&+-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_query, re.IGNORECASE)
        if match:
            value = match.group(1).strip(" ,.")
            value = re.sub(r"^(show|find|list|who are|who is|give me|candidates with|candidates having)\s+", "", value, flags=re.IGNORECASE)
            if value:
                return value

    for marker in [
        "btech", "b.tech", "be ", "b.e", "mtech", "m.tech", "mca", "bca", "bsc", "msc",
        "phd", "diploma", "graduate", "graduation", "undergraduate", "bachelor", "bachelors",
        "postgraduate", "post graduation", "master", "masters",
        "civil engineering", "computer science", "computer applications",
        "structural engineering", "geology", "environmental engineering", "amie",
    ]:
        if marker in lowered:
            return raw_query
    return None


def _extract_skill_filters(user_query: str) -> tuple[list[str], list[str]]:
    raw_query = " ".join(user_query.split())
    includes = []
    excludes = []

    negative_patterns = [
        r"not\s+([a-z0-9 .#+/\-]+)",
        r"without\s+([a-z0-9 .#+/\-]+)",
        r"excluding\s+([a-z0-9 .#+/\-]+)",
    ]
    for pattern in negative_patterns:
        for match in re.finditer(pattern, raw_query, re.IGNORECASE):
            value = match.group(1).strip(" ,.")
            if value:
                excludes.append(value)

    positive_patterns = [
        r"exactly\s+([a-z0-9 .#+/\-]+?)(?:\s+but\s+not|\s*$)",
        r"with\s+([a-z0-9 .#+/\-]+?)\s+skills?",
        r"skilled in\s+([a-z0-9 .#+/\-]+)",
        r"experience in\s+([a-z0-9 .#+/\-]+)",
        r"expertise in\s+([a-z0-9 .#+/\-]+)",
        r"know(?:ledge)? of\s+([a-z0-9 .#+/\-]+)",
    ]
    for pattern in positive_patterns:
        for match in re.finditer(pattern, raw_query, re.IGNORECASE):
            value = match.group(1).strip(" ,.")
            if value:
                includes.append(value)

    both_match = re.search(r"both\s+([a-z0-9 .#+/\-]+?)\s+and\s+([a-z0-9 .#+/\-]+)", raw_query, re.IGNORECASE)
    if both_match:
        includes.extend([both_match.group(1).strip(" ,."), both_match.group(2).strip(" ,.")])

    for tech in ["python", "java", "sql", "power bi", "react", "survey", "design", "tunnel design", "civil engineering"]:
        if re.search(rf"\b{re.escape(tech)}\b", raw_query, re.IGNORECASE):
            if tech not in " ".join(includes).lower() and tech not in " ".join(excludes).lower():
                if f"not {tech}" in raw_query.lower() or f"without {tech}" in raw_query.lower():
                    excludes.append(tech)
                elif "skill" in raw_query.lower() or "experience" in raw_query.lower() or "expertise" in raw_query.lower():
                    includes.append(tech)

    return _unique_preserve(includes), _unique_preserve(excludes)


def _extract_domain_phrase(user_query: str) -> Optional[str]:
    raw_query = " ".join(user_query.split())
    patterns = [
        r"(?:of|in|from)\s+([\w\s./&+-]+?)\s+domain\b",
        r"\bdomain\s+of\s+([\w\s./&+-]+)",
        r"\bdomain\s+in\s+([\w\s./&+-]+)",
        r"\bindustry\s+of\s+([\w\s./&+-]+)",
        r"\bsector\s+of\s+([\w\s./&+-]+)",
        r"\bexperience\s+in\s+([\w\s./&+-]+?)(?:\s+(?:projects?|work|sector|industry|domain)\b|$)",
        r"\bworked\s+on\s+([\w\s./&+-]+?)(?:\s+projects?\b|$)",
        r"\bexposure\s+to\s+([\w\s./&+-]+?)(?:\s+(?:projects?|work|sector|industry)\b|$)",
        r"\b(?:with|having)\s+([\w\s./&+-]+?)\s+projects?\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_query, re.IGNORECASE)
        if not match:
            continue
        value = match.group(1).strip(" ,.")
        value = re.sub(
            r"^(show|find|list|all|the|candidate|candidates|resume|resumes|who are|who is|give me)\s+",
            "",
            value,
            flags=re.IGNORECASE,
        ).strip(" ,.")
        if value:
            return value
    return None


def _interpret_resume_query(user_query: str) -> ResumeQueryInterpretation:
    experience_operator, experience_value, experience_upper = _extract_experience_filter(user_query)
    education_query = _extract_education_phrase(user_query)
    skill_queries, excluded_skill_queries = _extract_skill_filters(user_query)

    domain_query = None
    lowered = user_query.lower()
    if any(marker in lowered for marker in ["domain", "industry", "sector"]):
        domain_query = _extract_domain_phrase(user_query) or user_query
    elif not education_query and not skill_queries:
        extracted_domain = _extract_domain_phrase(user_query)
        query_tokens = set(_tokenize_lookup_text(user_query))
        if extracted_domain:
            domain_query = extracted_domain
        elif query_tokens & DOMAIN_HINT_TERMS:
            domain_query = user_query

    notes = []
    if education_query and "background" in lowered:
        notes.append("Mapped 'background' to education/qualification filter.")
    if experience_operator == "gt":
        notes.append("Interpreted 'more than/over/above' as strict greater-than.")
    if experience_operator == "between":
        notes.append("Interpreted range as inclusive between.")
    if domain_query and not any(marker in lowered for marker in ["domain", "industry", "sector"]):
        notes.append("Inferred an implicit domain/project-context filter from the query wording.")

    return ResumeQueryInterpretation(
        original_query=user_query,
        experience_operator=experience_operator,
        experience_value=experience_value,
        experience_upper_value=experience_upper,
        education_query=education_query,
        skill_queries=skill_queries,
        excluded_skill_queries=excluded_skill_queries,
        domain_query=domain_query,
        intent_notes=notes,
    )


def _domain_clause(model, term: str, param_prefix: str):
    normalized_term = _normalize_lookup_text(term)
    if not normalized_term:
        return None
    normalized_compact = normalized_term.replace(" ", "")
    if len(normalized_compact) <= 2:
        clause = text(
            f"""
            EXISTS (
                SELECT 1
                FROM json_each({model.__tablename__}.domain_expertise)
                WHERE lower(replace(replace(json_each.value, '_', ' '), ' ', '')) = :{param_prefix}_exact
            )
            """
        ).bindparams(**{f"{param_prefix}_exact": normalized_compact})
        return clause

    clause = text(
        f"""
        EXISTS (
            SELECT 1
            FROM json_each({model.__tablename__}.domain_expertise)
            WHERE lower(replace(json_each.value, '_', ' ')) = :{param_prefix}_exact
               OR lower(replace(json_each.value, '_', ' ')) LIKE :{param_prefix}_phrase
        )
        """
    ).bindparams(
        **{
            f"{param_prefix}_exact": normalized_term,
            f"{param_prefix}_phrase": f"%{normalized_term}%",
        }
    )
    return clause


def _matches_experience_filter(value: float, operator: Optional[str], lower: Optional[float], upper: Optional[float]) -> bool:
    if operator is None or lower is None:
        return True
    if operator == "gt":
        return value > lower
    if operator == "gte":
        return value >= lower
    if operator == "lt":
        return value < lower
    if operator == "lte":
        return value <= lower
    if operator == "eq":
        return value == lower
    if operator == "between" and upper is not None:
        return lower <= value <= upper
    return True


def _apply_standardized_json_filter(query, column, values: list[str]):
    if not values:
        return query.filter(False)
    like_clauses = [column.like(f'%"{value}"%') for value in values]
    return query.filter(or_(*like_clauses))


def filter_by_derived_profile_flag(query, model, flag_name: str):
    """Filter where parsed_data->'$.derived_profile.<flag_name>' is true."""
    clause = text(f"json_extract({model.__tablename__}.parsed_data, '$.derived_profile.{flag_name}') = 1")
    return query.filter(clause)


def filter_by_component(query, model, component: str):
    """Filter where an experience item component matches or if skills match."""
    return query.filter(model.parsed_data.ilike(f"%{component}%"))


def filter_by_sector(query, model, sector: str):
    """Filter by sector or subsector within experience JSON."""
    return query.filter(
        or_(
            model.parsed_data.ilike(f'%"sector": "{sector}"%'),
            model.parsed_data.ilike(f'%"subsector": "{sector}"%'),
        )
    )


def filter_by_min_project_value(query, model, min_value_cr: float):
    """Filter where derived_profile.max_project_value_cr >= min_value_cr."""
    clause = text(
        f"json_extract({model.__tablename__}.parsed_data, '$.derived_profile.max_project_value_cr') >= :val"
    )
    return query.filter(clause).params(val=min_value_cr)


def filter_by_client_type(query, model, client_type: str):
    """Filter where an experience item client_type matches."""
    return query.filter(model.parsed_data.ilike(f'%"client_type": "{client_type}"%'))


@tool
def get_common_values(category: str) -> str:
    """Get the list of all standardized common values for a category ('skills' or 'education')."""
    db = SessionLocal()
    try:
        if category not in {"skills", "education"}:
            return "Invalid category. Use 'skills' or 'education'."

        items = _load_common_items(db, category)
        if not items:
            return f"No common {category} found in database yet."

        lines = []
        for item in items:
            aliases = ", ".join(item["aliases"]) if item["aliases"] else "none"
            label = item.get("display_label", item["name"])
            lines.append(f"- {item['name']} | label: {label} (aliases: {aliases})")
        return f"Standardized {category}:\n" + "\n".join(lines)
    finally:
        db.close()


@tool
def get_resume_detail(resume_id: int) -> str:
    """Get full details of a specific resume by ID."""
    db = SessionLocal()
    try:
        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        if not resume:
            return f"Resume ID {resume_id} not found."

        parsed = json.loads(resume.parsed_data) if resume.parsed_data else {}
        experience = parsed.get("experience", [])
        exp_text = "\n".join(
            f"  - {item.get('role')} at {item.get('company')} ({item.get('duration')})"
            for item in experience
        )
        return (
            f"**{resume.name}** (ID:{resume.id})\n"
            f"Email: {resume.email or 'N/A'} | Phone: {resume.phone or 'N/A'}\n"
            f"Experience: {resume.total_years_experience} years\n"
            f"Skills: {', '.join(json.loads(resume.skills))}\n"
            f"Education: {', '.join(json.loads(resume.education))}\n"
            f"Certifications: {', '.join(json.loads(resume.certifications))}\n"
            f"Domain: {', '.join(json.loads(resume.domain_expertise))}\n"
            f"Standardized Skills: {', '.join(json.loads(resume.standardized_skills))}\n"
            f"Standardized Education: {', '.join(json.loads(resume.standardized_education))}\n"
            f"Work History:\n{exp_text}"
        )
    finally:
        db.close()


@tool
def get_tender_detail(tender_id: int) -> str:
    """Get full details of a specific tender by ID."""
    db = SessionLocal()
    try:
        tender = db.query(Tender).filter(Tender.id == tender_id).first()
        if not tender:
            return f"Tender ID {tender_id} not found."

        roles = json.loads(tender.required_roles) if tender.required_roles else []
        techs = json.loads(tender.key_technologies) if tender.key_technologies else []
        eligibility = json.loads(tender.eligibility_criteria) if tender.eligibility_criteria else []

        role_lines = []
        for role in roles:
            role_title = role.get("role_title") or "N/A"
            min_experience = role.get("min_experience", 0)
            required_skills = role.get("required_skills", []) or []
            required_certs = role.get("required_certifications", []) or []
            required_domain = role.get("required_domain", []) or []
            preferred_components = role.get("preferred_components", []) or []
            min_project_value_cr = role.get("min_project_value_cr", 0)
            client_type_pref = role.get("client_type_preference")

            role_lines.append(f"  - {role_title}")
            role_lines.append(f"    - Min Experience: {min_experience}+ yrs")
            role_lines.append(f"    - Required Skills: {', '.join(required_skills) if required_skills else 'N/A'}")
            role_lines.append(f"    - Required Certifications: {', '.join(required_certs) if required_certs else 'N/A'}")
            role_lines.append(f"    - Required Domain: {', '.join(required_domain) if required_domain else 'N/A'}")
            role_lines.append(f"    - Preferred Components: {', '.join(preferred_components) if preferred_components else 'N/A'}")
            role_lines.append(f"    - Min Project Value: {min_project_value_cr or 0} Cr")
            role_lines.append(f"    - Client Type Preference: {client_type_pref or 'N/A'}")

        roles_text = "\n".join(role_lines)
        eligibility_text = "\n".join(f"  - {item}" for item in eligibility[:30]) if eligibility else "  - N/A"
        return (
            f"**TND-{tender.id:04d}** | {tender.project_name}\n"
            f"Client: {tender.client or 'N/A'} | Duration: {tender.project_duration or 'N/A'}\n"
            f"Ref: {tender.document_reference or 'N/A'} | Date: {tender.document_date or 'N/A'}\n"
            f"File: {tender.file_name}\n"
            f"Technologies: {', '.join(techs)}\n"
            f"Eligibility Criteria ({len(eligibility)}):\n{eligibility_text}\n"
            f"Roles ({len(roles)}):\n{roles_text}"
        )
    finally:
        db.close()


def _expand_domain_query(domain_query: str) -> list[str]:
    """Use world knowledge and AI to expand professional domain terms into related concepts.
    This ensures we match candidates' specific expertise even when the user uses a broad term.
    """
    if not domain_query:
        return []
    
    q_norm = domain_query.lower().strip()
    llm = get_reasoning_llm()
    
    # AI-native expansion of professional concepts
    prompt = f"""Given the professional/industry domain query: "{domain_query}"
1. If it's a short acronym (like IT, EPC, CS), expand it.
2. Generate 8-10 related professional domain keywords, synonyms, or technical specialties that a relevant candidate might have in their resume.
3. Return ONLY a comma-separated list of lowercase strings.
4. No preamble or explanation.
"""
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        concepts = [c.strip().lower() for c in response.content.split(",") if c.strip()]
        if q_norm not in concepts:
            concepts.append(q_norm)
        # Ensure we don't have extremely short words that could cause collision (except the acronym itself)
        return [c for c in concepts if len(c) > 2 or c == q_norm]
    except Exception:
        return [q_norm]


@tool
def sql_query_resumes(
    min_experience: Optional[float] = None,
    skills: Optional[str] = None,
    domain: Optional[str] = None,
    education: Optional[str] = None,
) -> str:
    """Query resumes with structured filters."""
    db = SessionLocal()
    try:
        query = db.query(Resume)
        base_query = query
        if min_experience:
            query = query.filter(Resume.total_years_experience >= min_experience)
            base_query = base_query.filter(Resume.total_years_experience >= min_experience)

        resolved_skills = []
        resolved_education = []

        if skills:
            skill_items = _load_common_items(db, "skills")
            resolved_skills = _resolve_common_values("skills", skills, skill_items)
            if resolved_skills and resolved_skills[0].startswith("HITL_CHOICES:"):
                return f"I need clarification on the skills: {resolved_skills[0].replace('HITL_CHOICES:', '').strip()}"
            query = _apply_standardized_json_filter(query, Resume.standardized_skills, resolved_skills)
            base_query = _apply_standardized_json_filter(base_query, Resume.standardized_skills, resolved_skills)

        if education:
            education_items = _load_common_items(db, "education")
            resolved_education = _resolve_common_values("education", education, education_items)
            if resolved_education and resolved_education[0].startswith("HITL_CHOICES:"):
                return f"I found several matching qualifications. Which one are you looking for? {resolved_education[0].replace('HITL_CHOICES:', '').strip()}"
            query = _apply_standardized_json_filter(query, Resume.standardized_education, resolved_education)

        if domain:
            extracted_domain = _extract_domain_phrase(domain) or domain
            expanded_domains = _expand_domain_query(extracted_domain)
            domain_filters = []
            for idx, d in enumerate(expanded_domains):
                clause = _domain_clause(Resume, d, f"domain_{idx}")
                if clause is not None:
                    domain_filters.append(clause)

            if domain_filters:
                query = query.filter(or_(*domain_filters))
                base_query = base_query.filter(or_(*domain_filters))

        resumes = query.all()
        fallback_note = None
        if education:
            resumes_by_id = {resume.id: resume for resume in resumes}
            for resume in base_query.all():
                if resume.id in resumes_by_id:
                    continue
                if _resume_matches_education_query(resume, education, resolved_education):
                    resumes_by_id[resume.id] = resume
            if len(resumes_by_id) != len(resumes):
                fallback_note = "Education raw-text fallback added candidates whose standardized education is missing or outdated."
            resumes = list(resumes_by_id.values())
        results = []
        for resume in resumes:
            parsed = json.loads(resume.parsed_data) if resume.parsed_data else {}
            experience = parsed.get("experience", [])
            current_role = experience[0].get("role", "N/A") if experience else "N/A"
            raw_skills = json.loads(resume.skills) if resume.skills else []
            education_list = json.loads(resume.education) if resume.education else []
            std_edu = json.loads(resume.standardized_education) if resume.standardized_education else []
            photo_url = f"/api/resumes/photo/{resume.photo_filename}" if resume.photo_filename else ""
            results.append(
                f"- {resume.name} (ID:{resume.id}) | {current_role} | "
                f"{resume.total_years_experience} yrs | "
                f"Education: {', '.join(education_list)} | "
                f"Std-Edu: {', '.join(std_edu)} | "
                f"Photo: {photo_url} | "
                f"Skills: {', '.join(raw_skills[:8])}"
            )

        header_parts = []
        if skills:
            header_parts.append(
                f"Resolved skill common values: {', '.join(resolved_skills) if resolved_skills else 'none'}"
            )
        if education:
            header_parts.append(
                f"Resolved education common values: {', '.join(resolved_education) if resolved_education else 'none'}"
            )
        if fallback_note:
            header_parts.append(fallback_note)

        try:
            compiled_sql = str(query.statement.compile(compile_kwargs={"literal_binds": True}))
        except Exception as exc:
            compiled_sql = f"Could not compile SQL: {exc}"

        if not results:
            header = "\n".join(header_parts) if header_parts else ""
            return f"{header}\nGenerated SQL:\n```sql\n{compiled_sql}\n```\nNo resumes match the filters."

        response_parts = []
        if header_parts:
            response_parts.append("\n".join(header_parts))
        response_parts.append(f"Generated SQL:\n```sql\n{compiled_sql}\n```")
        response_parts.append("\n".join(results[:20]))
        return "\n".join(response_parts)
    finally:
        db.close()


@tool
def query_resumes_dynamic(query: str) -> str:
    """Interpret a natural-language resume query into strict structured filters and return validated results.
    Use this for user questions combining education/background, skills, and experience constraints.
    """
    db = SessionLocal()
    try:
        interpretation = _interpret_resume_query(query)
        base_query = db.query(Resume)

        if interpretation.experience_operator in {"gt", "gte", "eq"} and interpretation.experience_value is not None:
            threshold = interpretation.experience_value
            if interpretation.experience_operator == "gt":
                base_query = base_query.filter(Resume.total_years_experience > threshold)
            elif interpretation.experience_operator == "gte":
                base_query = base_query.filter(Resume.total_years_experience >= threshold)
            elif interpretation.experience_operator == "eq":
                base_query = base_query.filter(Resume.total_years_experience == threshold)
        elif interpretation.experience_operator in {"lt", "lte"} and interpretation.experience_value is not None:
            threshold = interpretation.experience_value
            if interpretation.experience_operator == "lt":
                base_query = base_query.filter(Resume.total_years_experience < threshold)
            else:
                base_query = base_query.filter(Resume.total_years_experience <= threshold)
        elif interpretation.experience_operator == "between" and interpretation.experience_value is not None and interpretation.experience_upper_value is not None:
            base_query = base_query.filter(
                Resume.total_years_experience >= interpretation.experience_value,
                Resume.total_years_experience <= interpretation.experience_upper_value,
            )

        skill_items = _load_common_items(db, "skills")
        education_items = _load_common_items(db, "education")
        resolved_education = (
            _resolve_common_values("education", interpretation.education_query, education_items)
            if interpretation.education_query else []
        )

        candidates = base_query.all()
        validated = []
        for resume in candidates:
            if not _matches_experience_filter(
                resume.total_years_experience or 0.0,
                interpretation.experience_operator,
                interpretation.experience_value,
                interpretation.experience_upper_value,
            ):
                continue

            if interpretation.education_query and not _resume_matches_education_query(
                resume, interpretation.education_query, resolved_education
            ):
                continue

            if interpretation.skill_queries and not all(
                _resume_matches_skill_query(resume, skill_query, skill_items)
                for skill_query in interpretation.skill_queries
            ):
                continue

            if interpretation.excluded_skill_queries and any(
                _resume_matches_skill_query(resume, skill_query, skill_items)
                for skill_query in interpretation.excluded_skill_queries
            ):
                continue

            if interpretation.domain_query and not _resume_matches_domain_phrase(resume, interpretation.domain_query):
                continue

            validated.append(resume)

        try:
            compiled_sql = str(base_query.statement.compile(compile_kwargs={"literal_binds": True}))
        except Exception as exc:
            compiled_sql = f"Could not compile SQL: {exc}"

        lines = [
            f"Interpreted Query: {interpretation.model_dump_json()}",
            f"Generated SQL:\n```sql\n{compiled_sql}\n```",
        ]
        if resolved_education:
            lines.append(f"Resolved education common values: {', '.join(resolved_education)}")

        if not validated:
            lines.append("No resumes match the validated filters.")
            return "\n".join(lines)

        for resume in validated[:20]:
            parsed = json.loads(resume.parsed_data) if resume.parsed_data else {}
            experience = parsed.get("experience", [])
            current_role = experience[0].get("role", "N/A") if experience else "N/A"
            raw_skills = json.loads(resume.skills) if resume.skills else []
            education_list = json.loads(resume.education) if resume.education else []
            std_edu = json.loads(resume.standardized_education) if resume.standardized_education else []
            photo_url = f"/api/resumes/photo/{resume.photo_filename}" if resume.photo_filename else ""
            lines.append(
                f"- {resume.name} (ID:{resume.id}) | {current_role} | "
                f"{resume.total_years_experience} yrs | "
                f"Education: {', '.join(education_list)} | "
                f"Std-Edu: {', '.join(std_edu)} | "
                f"Photo: {photo_url} | "
                f"Skills: {', '.join(raw_skills[:8])}"
            )
        return "\n".join(lines)
    finally:
        db.close()


@tool
def get_match_results(tender_id: int, role_title: Optional[str] = None) -> str:
    """Get existing match results for a tender."""
    db = SessionLocal()
    try:
        query = db.query(MatchResult).filter(MatchResult.tender_id == tender_id)
        if role_title:
            query = query.filter(MatchResult.role_title == role_title)
        matches = query.order_by(MatchResult.final_score.desc()).limit(20).all()

        if not matches:
            return f"No match results found for tender {tender_id}."

        results = []
        for match in matches:
            resume = db.query(Resume).filter(Resume.id == match.resume_id).first()
            name = resume.name if resume else "Unknown"
            photo_url = f"/api/resumes/photo/{resume.photo_filename}" if resume and resume.photo_filename else ""
            designation = "N/A"
            experience_years = resume.total_years_experience if resume else 0
            if resume and resume.parsed_data:
                try:
                    parsed = json.loads(resume.parsed_data)
                    exp = parsed.get("experience", [])
                    designation = exp[0].get("role", "N/A") if exp else "N/A"
                except Exception:
                    designation = "N/A"
            explanation = match.llm_explanation or "No explanation available."
            strengths = json.loads(match.strengths) if match.strengths else []
            try:
                breakdown = json.loads(match.score_breakdown) if match.score_breakdown else {}
            except Exception:
                breakdown = {}
            
            # Use a more explicit single-line format for high visibility
            summary = (
                f"- Candidate: {name} | Resume ID: {match.resume_id} | Role: {match.role_title} | "
                f"Designation: {designation} | Experience: {experience_years:g} yrs | "
                f"Photo URL: {photo_url} | Fit Score: {match.final_score:.1f}% | "
                f"Structured Score: {(match.structured_score or 0):.1f} | AI Score: {(match.llm_score or 0):.1f} | "
                f"Skills: {breakdown.get('skills', 0)} | Domain: {breakdown.get('domain', 0)} | "
                f"Edu: {breakdown.get('education', 0)} | Certs: {breakdown.get('certifications', 0)} | "
                f"Exp: {breakdown.get('experience', 0)} | "
                f"WHY BEST FIT: {explanation}"
            )
            if strengths:
                summary += f" | TOP STRENGTHS: {', '.join(strengths)}"
            
            results.append(summary)
        return "\n".join(results)
    finally:
        db.close()


@tool
def get_resume_inventory() -> str:
    """Get the exact current resume inventory with total count, IDs, names, and key summary fields.
    Use this for questions asking how many resumes exist, which candidates are available, or to list candidate names.
    """
    db = SessionLocal()
    try:
        resumes = db.query(Resume).order_by(Resume.id.asc()).all()
        lines = [f"RESUME INVENTORY SUMMARY:", f"- Total Resumes: {len(resumes)}"]
        for resume in resumes:
            parsed = json.loads(resume.parsed_data) if resume.parsed_data else {}
            experience = parsed.get("experience", [])
            current_role = experience[0].get("role", "N/A") if experience else "N/A"
            lines.append(
                f"- ID {resume.id}: {resume.name} | Role: {current_role} | Experience: {resume.total_years_experience:g} yrs"
            )
        return "\n".join(lines)
    finally:
        db.close()


@tool
def get_tender_inventory() -> str:
    """Get the exact current tender inventory with total count, IDs, and project names."""
    db = SessionLocal()
    try:
        tenders = db.query(Tender).order_by(Tender.id.asc()).all()
        lines = [f"TENDER INVENTORY SUMMARY:", f"- Total Tenders: {len(tenders)}"]
        for tender in tenders:
            lines.append(
                f"- TND-{tender.id:04d}: {tender.project_name} | Client: {tender.client or 'N/A'}"
            )
        return "\n".join(lines)
    finally:
        db.close()


@tool
def get_system_stats() -> str:
    """Get total counts of resumes and tenders currently stored in the system. 
    Use this to answer questions about 'how many' resumes or tenders exist in total.
    """
    db = SessionLocal()
    try:
        resume_count = db.query(Resume).count()
        tender_count = db.query(Tender).count()
        return (
            f"SYSTEM INVENTORY SUMMARY:\n"
            f"- Total Resumes: {resume_count}\n"
            f"- Total Tenders: {tender_count}\n"
        )
    finally:
        db.close()

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


class CommonValueSelection(BaseModel):
    selected_common_values: list[str] = Field(default_factory=list)
    reasoning: str = ""


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


def _education_query_constraints(user_query: str) -> dict:
    """Infer constraints for education queries. Simplified to rely on AI resolution."""
    return {
        "normalized": _normalize_lookup_text(user_query),
        "semantic_terms": set(_tokenize_lookup_text(user_query)),
    }


def _item_matches_education_constraints(item: dict, constraints: dict) -> bool:
    """Check if a catalog item matches the user query. Defer to AI resolution for complexity."""
    return True # Allow everything into the LLM context for final decision.


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

    llm = get_reasoning_llm().with_structured_output(CommonValueSelection)
    filtered_items = []
    catalog_lines = []
    for item in items:
        # Loosened pre-filter: Only skip if there's a clear, extreme mismatch (e.g. wrong level)
        # But for dev/small-db, we prefer showing MORE to the LLM to ensure dynamism.
        filtered_items.append(item)
        aliases = ", ".join(item["aliases"]) if item["aliases"] else "none"
        search_terms = ", ".join(item.get("search_terms", [])[:5]) if item.get("search_terms") else "none"
        level_part = f" | level: {item['level']}" if item.get("level") else ""
        catalog_lines.append(
            f"- {item['name']} | label: {item.get('display_label', item['name'])}{level_part} | concepts: {search_terms} | aliases: {aliases}"
        )

    if not catalog_lines:
        return []

    if category == "education":
        exact_matches = _catalog_exact_matches(category, user_query, filtered_items)
        if exact_matches:
            return exact_matches
    
    # Phase 1: Use AI to extract structured requirements (Level & Subject) from the user query
    # This keeps the "intelligence" dynamic without hardcoding degree names.
    extraction_prompt = (
        "You are an academic requirements analyst.\n"
        f"User Query: \"{user_query}\"\n\n"
        "Identify the core requirements:\n"
        "1. Academic Level: One of [graduate, postgraduate, phd, diploma] or null if not specified.\n"
        "2. Subject/Domain: The specific field of study (e.g. 'Civil Engineering') or null if not specified.\n"
        "3. Explicit Degrees: Any specific degree names mentioned (e.g. 'BTech').\n\n"
        "Return the analysis as JSON."
    )
    
    # We use a simpler, faster reasoning approach for extraction or reuse the LLM
    try:
        # Re-using the same LLM but with a custom structured output if needed
        # For brevity, let's assume we can derive the requirement specs.
        # But to be REALLY dynamic and robust, I'll use the LLM to select from the metadata-rich catalog
        # with a REVERSE instruction: "Select every entry whose METADATA Level matches the query intent."
        
        # Actually, let's just fix the prompt to be EXTREMELY explicit about the Selection Protocol.
        pass
    except:
        pass

    # REFINED AI PROMTP (The "registrar" approach)
    catalog_lines = []
    for item in items:
        name = item.get("name")
        if not name: continue
        level = item.get("level", "N/A")
        catalog_lines.append(f"- {name} (Technical Metadata Level: {level} | Concepts: {', '.join(item.get('concepts', []))})")

    catalog_text = "\n".join(catalog_lines)
    # Fetch unique levels present in the catalog for dynamic discoverability
    available_levels = sorted(list(set(item.get("level", "other") for item in items if item.get("level"))))
    
    prompt = (
        "You are an Academic Registrar standardizing search filters against a degree catalog.\n\n"
        f"User Filter: \"{user_query}\"\n"
        f"Catalog:\n{catalog_text}\n\n"
        f"AVAILABLE TECHNICAL LEVELS: {', '.join(available_levels)}\n\n"
        "SELECTION RULES (MANDATORY):\n"
        "1. DUAL-LEVEL RULE (PRIORITY): The level 'level_graduate_and_postgraduate' is a SUPERSET. You MUST select every entry with this level if the user is looking for EITHER 'graduate' level (Bachelors) OR 'postgraduate' level (Masters). This is non-negotiable for Integrated/Dual degrees.\n"
        "2. LEVEL DISCOVERY: Semantically identify the intended level from the user query. \n"
        "   - 'Graduation', 'Bachelors', 'Degree' -> graduate\n"
        "   - 'Masters', 'PG', 'Post Graduation' -> postgraduate\n"
        "3. SELECT EVERY IDENTIFIER where the 'Technical Metadata Level' matches the discovered intent.\n"
        "4. SUBJECT RULE: If a subject (e.g. 'Civil') is mentioned, select only those that match BOTH the level intent (or dual-level) AND the subject.\n"
        "5. Output: Return ONLY the list of matching technical identifiers (names)."
    )
    
    try:
        result = llm.invoke(prompt)
        selected = [value for value in result.selected_common_values if any(value == item["name"] for item in items)]
    except Exception as exc:
        logger.warning("LLM common-value resolution failed: %s", exc)
        selected = []

    if not selected:
        selected = _fallback_resolve_common_values(category, user_query, items)

    # HITL: Detect if the result is still too broad or ambiguous for a precise search
    if len(selected) > 5 or (not selected and items):
        # Generate choices for the agent to present to the user
        vague_terms = {"masters", "degree", "graduation", "post graduation", "postgraduation", "engineering", "bachelors"}
        if user_query.lower() in vague_terms or not selected:
            choices = []
            # Take a few top items or items related to the level if inferred
            limit = 6
            for item in items[:limit]:
                label = item.get("display_label", item["name"])
                choices.append(f"[[CHOICE: {label} | {item['name']} ]]")
            
            choice_str = " ".join(choices)
            logger.info("HITL triggered for %s. Choices: %s", category, choice_str)
            # We return this special string which the tool-calling logic will pass to the agent
            return [f"HITL_CHOICES: {choice_str}"]

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

    # Dynamically handle other subject/family synonyms
    # We use the generic semantic terms to broaden the search
    for subject in semantic_terms:
        if subject not in {"graduate", "postgraduate", "engineering"}:
             add(subject.replace("_", " "))

    return patterns


def _infer_education_level_from_terms(item_terms: set[str]) -> str:
    """Prioritize more advanced degrees over lower ones."""
    if "phd" in item_terms or "doctorate" in item_terms:
        return "phd"
    if "postgraduate" in item_terms or "master" in item_terms or "master_engineering" in item_terms:
        return "postgraduate"
    if "graduate" in item_terms or "bachelor" in item_terms or "bachelor_engineering" in item_terms:
        return "graduate"
    if "diploma" in item_terms:
        return "diploma"
    if "highschool" in item_terms:
        return "highschool"
    return "other"


def _education_entry_matches_query(entry: str, user_query: str) -> bool:
    """Robust fallback for resumes with messy raw data bypassing standardization."""
    normalized_entry = _normalize_lookup_text(entry)
    normalized_query = _normalize_lookup_text(user_query)
    if not normalized_entry or not normalized_query:
        return False
        
    query_words = normalized_query.split()
    if not query_words: return False

    # Stricter check: All (or most) query words must be present
    match_count = sum(1 for word in query_words if word in normalized_entry)
    return (match_count / len(query_words)) >= 0.7


def _resume_matches_education_query(resume: Resume, user_query: str, resolved_education: list[str]) -> bool:
    standardized_education = json.loads(resume.standardized_education) if resume.standardized_education else []
    if any(value in standardized_education for value in resolved_education):
        return True

    raw_education_entries = json.loads(resume.education) if resume.education else []
    if not raw_education_entries:
        return False

    return any(_education_entry_matches_query(entry, user_query) for entry in raw_education_entries)


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
        roles_text = "\n".join(
            f"  - {role.get('role_title')}: {role.get('min_experience', 0)}+ yrs, Skills: {', '.join(role.get('required_skills', []))}"
            for role in roles
        )
        return (
            f"**TND-{tender.id:04d}** | {tender.project_name}\n"
            f"Client: {tender.client or 'N/A'} | Duration: {tender.project_duration or 'N/A'}\n"
            f"Ref: {tender.document_reference or 'N/A'} | Date: {tender.document_date or 'N/A'}\n"
            f"Technologies: {', '.join(techs)}\n"
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
            expanded_domains = _expand_domain_query(domain)
            domain_filters = []
            for d in expanded_domains:
                domain_filters.append(Resume.domain_expertise.ilike(f"%{d}%"))
                domain_filters.append(Resume.standardized_education.ilike(f"%{d}%"))
            
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

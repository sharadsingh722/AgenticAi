"""Multi-pass extraction agent using LangGraph.

Graph: build_structure → deep_extract → self_verify → [has_issues?] → fix_issues → END
"""
import json
import logging
import re
from typing import Optional, List, Dict, TypedDict

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

from app.services.llm import get_fast_llm, get_reasoning_llm
from app.schemas import ResumeParseResult, TenderParseResult
from app.database import SessionLocal
from app.models import CommonSkill, CommonEducation
from app.prompts.resume_prompts import (
    RESUME_STRUCTURE_PROMPT, RESUME_DEEP_EXTRACT_PROMPT,
    RESUME_VERIFICATION_PROMPT, RESUME_FIX_ISSUES_PROMPT,
    RESUME_EDU_CLASSIFIER_PROMPT, RESUME_EDU_FALLBACK_PROMPT,
    RESUME_NORMALIZER_PROMPT
)
from app.prompts.tender_prompts import (
    TENDER_DEEP_EXTRACT_PROMPT, TENDER_VERIFICATION_PROMPT, TENDER_FIX_ISSUES_PROMPT
)
from app.utils.profile_engine import compute_derived_profile

logger = logging.getLogger(__name__)


# --- State ---

class ExtractionState(TypedDict):
    raw_text: str
    doc_type: str  # "resume" or "tender"
    document_structure: str
    sections: List[Dict]
    extracted_data: Dict
    verification_issues: List[str]
    is_verified: bool
    final_data: Dict
    pass_count: int
    error: Optional[str]


# --- Nodes ---

def build_structure(state: ExtractionState) -> dict:
    """Pass 1: Identify document sections. Skip for short documents (resumes) to save time."""
    doc_type = state["doc_type"]
    text_len = len(state["raw_text"])

    # Skip structure analysis for short docs (resumes are typically < 20K chars)
    if doc_type == "resume" or text_len < 20000:
        return {
            "document_structure": "{}",
            "sections": [],
            "pass_count": 1,
        }

    llm = get_fast_llm()
    text_sample = state["raw_text"][:5000]

    prompt = RESUME_STRUCTURE_PROMPT.format(text_sample=text_sample, doc_type=doc_type)

    result = llm.invoke([HumanMessage(content=prompt)])
    try:
        structure = json.loads(result.content.strip().strip("`").strip())
    except Exception:
        structure = {"sections": [], "summary": "Could not parse structure"}

    return {
        "document_structure": json.dumps(structure),
        "sections": structure.get("sections", []),
        "pass_count": 1,
    }





def _deep_extract_tender(raw_text: str) -> dict:
    """Extract tender data using chunked approach (proven from v1)."""
    llm = get_reasoning_llm()

    # Chunk the text for long documents
    max_chars = 100000
    chunks = []
    text = raw_text
    while text:
        if len(text) <= max_chars:
            chunks.append(text)
            break
        split_at = text.rfind("\n\n", 0, max_chars)
        if split_at == -1:
            split_at = text.rfind("\n", 0, max_chars)
        if split_at == -1:
            split_at = max_chars
        chunks.append(text[:split_at])
        text = text[split_at:].strip()

    all_roles = []
    all_criteria = []
    all_technologies = []
    project_name = "Unknown Project"
    client = None
    doc_ref = None
    doc_date = None
    project_duration = None

    for i, chunk in enumerate(chunks):
        prompt = TENDER_DEEP_EXTRACT_PROMPT.format(text=chunk)
        result = llm.invoke([HumanMessage(content=prompt)])
        try:
            content = result.content.strip()
            if content.startswith("```"):
                content = content[content.index("\n") + 1:]
            if content.endswith("```"):
                content = content[:-3]
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                data = json.loads(content[start:end + 1])
            else:
                continue
        except Exception:
            continue

        if i == 0:
            project_name = data.get("project_name", project_name)
            client = data.get("client", client)
            doc_ref = data.get("document_reference", doc_ref)
            doc_date = data.get("document_date", doc_date)
            project_duration = data.get("project_duration", project_duration)

        all_roles.extend(data.get("required_roles", []))
        all_criteria.extend(data.get("eligibility_criteria", []))
        all_technologies.extend(data.get("key_technologies", []))

    # Deduplicate roles by title
    seen = set()
    unique_roles = []
    for role in all_roles:
        key = role.get("role_title", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique_roles.append(role)

    return {
        "extracted_data": {
            "project_name": project_name,
            "client": client,
            "document_reference": doc_ref,
            "document_date": doc_date,
            "required_roles": unique_roles,
            "eligibility_criteria": list(set(all_criteria)),
            "project_duration": project_duration,
            "key_technologies": list(set(all_technologies)),
        },
        "pass_count": 2,
    }


def _get_master_data_context() -> str:
    """Fetch current common skills and education to provide context for AI resolution."""
    db = SessionLocal()
    try:
        skills = db.query(CommonSkill).all()
        edu = db.query(CommonEducation).all()
        
        context = "### MASTER COMMON DATA (Existing entities in database)\n\n"
        
        context += "Common Skills:\n"
        if not skills:
            context += "- None yet\n"
        for s in skills:
            aliases = json.loads(s.aliases) if s.aliases else []
            context += f"- {s.name} (aliases: {', '.join(aliases)})\n"
            
        context += "\nCommon Education/Degrees:\n"
        if not edu:
            context += "- None yet\n"
        for e in edu:
            aliases = json.loads(e.aliases) if e.aliases else []
            context += f"- {e.name} (aliases: {', '.join(aliases)})\n"
            
        return context
    except Exception as e:
        logger.error(f"Failed to fetch master data: {e}")
        return "### MASTER COMMON DATA\n(Error fetching master data, proceed with new resolutions if needed)"
    finally:
        db.close()


def deep_extract(state: ExtractionState) -> dict:
    """Pass 2: Deep extraction using reasoning model.

    For tenders: uses chunked extraction (proven approach from v1) + focused role extraction.
    For resumes: single-pass extraction.
    """
    doc_type = state["doc_type"]
    raw_text = state["raw_text"]

    if doc_type == "tender":
        return _deep_extract_tender(raw_text)

    llm = get_reasoning_llm()
    text = raw_text[:50000]

    if doc_type == "resume":
        master_data_context = _get_master_data_context()
        prompt = RESUME_DEEP_EXTRACT_PROMPT.format(master_data_context=master_data_context, text=text)
    else:
        prompt = TENDER_DEEP_EXTRACT_PROMPT.format(text=text)

    result = llm.invoke([HumanMessage(content=prompt)])

    try:
        # Parse JSON from response
        content = result.content.strip()
        if content.startswith("```"):
            content = content[content.index("\n") + 1:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            data = json.loads(content[start:end + 1])
        else:
            data = json.loads(content)
    except Exception as e:
        logger.error(f"Deep extract parse failed: {e}")
        data = {}

    return {
        "extracted_data": data,
        "pass_count": 2,
    }


def self_verify(state: ExtractionState) -> dict:
    """Pass 3: Verify extraction against raw text using fast model."""
    llm = get_fast_llm()
    doc_type = state["doc_type"]
    data = state["extracted_data"]
    raw_snippet = state["raw_text"][:8000]

    if doc_type == "resume":
        check_prompt = RESUME_VERIFICATION_PROMPT.format(
            name=data.get('name'),
            skill_count=len(data.get('skills', [])),
            skills_snippet=', '.join(data.get('skills', [])[:10]),
            exp_count=len(data.get('experience', [])),
            years=data.get('total_years_experience'),
            education=data.get('education', []),
            raw_snippet=raw_snippet
        )
    else:
        roles = data.get("required_roles", [])
        check_prompt = TENDER_VERIFICATION_PROMPT.format(
            project_name=data.get('project_name'),
            client=data.get('client'),
            role_count=len(roles),
            roles_snippet=[r.get('role_title') for r in roles],
            technologies=data.get('key_technologies', []),
            raw_snippet=raw_snippet
        )

    result = llm.invoke([HumanMessage(content=check_prompt)])
    try:
        content = result.content.strip().strip("`").strip()
        start = content.find("{")
        end = content.rfind("}")
        verification = json.loads(content[start:end + 1])
    except Exception:
        verification = {"issues": [], "is_valid": True}

    return {
        "verification_issues": verification.get("issues", []),
        "is_verified": verification.get("is_valid", True),
        "pass_count": 3,
    }


def fix_issues(state: ExtractionState) -> dict:
    """Fix identified issues using fast model (speed optimization)."""
    llm = get_fast_llm()
    issues = state["verification_issues"]
    data = state["extracted_data"]
    raw_snippet = state["raw_text"][:15000]

    doc_type = state.get("doc_type", "resume")
    if doc_type == "resume":
        prompt = RESUME_FIX_ISSUES_PROMPT.format(
            issues_json=json.dumps(issues, indent=2),
            data_json=json.dumps(data, indent=2)[:3000],
            raw_snippet=raw_snippet
        )
    else:
        prompt = TENDER_FIX_ISSUES_PROMPT.format(
            issues_json=json.dumps(issues, indent=2),
            data_json=json.dumps(data, indent=2)[:3000],
            raw_snippet=raw_snippet
        )

    result = llm.invoke([HumanMessage(content=prompt)])
    try:
        content = result.content.strip()
        if content.startswith("```"):
            content = content[content.index("\n") + 1:]
        if content.endswith("```"):
            content = content[:-3]
        start = content.find("{")
        end = content.rfind("}")
        fixed = json.loads(content[start:end + 1])
    except Exception:
        fixed = data  # Fallback to original

    return {"final_data": fixed}


# --- Conditional ---

def has_issues(state: ExtractionState) -> str:
    issues = state.get("verification_issues", [])
    # Only trigger fix for critical issues (name wrong, major data missing)
    # Skip fix for minor issues like "could have more skills" to save time and avoid data corruption
    critical_keywords = ["name", "wrong", "incorrect", "missing entirely", "not found", "zero experience"]
    has_critical = any(
        any(kw in issue.lower() for kw in critical_keywords)
        for issue in issues
    )
    if has_critical:
        return "fix_issues"
    return END


# --- Post-processing ---

def _calculate_experience_from_dates(experience: list) -> float:
    """Calculate total years from experience entries by finding earliest start date.
    Only counts entries that look like real jobs (at a company).
    """
    earliest_year = None
    for exp in experience:
        if not isinstance(exp, dict): continue
        role = (exp.get("role") or "").lower()
        company = (exp.get("company") or "").lower()
        
        # Skip items that are likely academic projects or non-professional
        skip_terms = {"project", "academic", "student", "learning", "training", "coursework", "hackathon"}
        if any(term in role for term in skip_terms) or company in {"n/a", "none", "", "university", "college"}:
            continue

        duration = exp.get("duration", "")
        # Find 4-digit years (1960-2026) anywhere in the string
        year_matches = re.findall(r'((?:19|20)\d{2})', duration)
        for y_str in year_matches:
            yr = int(y_str)
            if 1960 <= yr <= 2026:
                if earliest_year is None or yr < earliest_year:
                    earliest_year = yr

    if earliest_year:
        return round(2026 - earliest_year, 1)
    return 0.0


def _extract_education_with_targeted_llm(raw_text: str) -> dict:
    """Fallback education extraction for noisy OCR/table resumes."""
    keyword_patterns = [
        r"qualification details",
        r"academic qualification",
        r"education",
        r"degree",
        r"university",
        r"college",
        r"diploma",
    ]

    snippets = []
    lowered = raw_text.lower()
    for pattern in keyword_patterns:
        match = re.search(pattern, lowered)
        if match:
            start = max(0, match.start() - 250)
            end = min(len(raw_text), match.start() + 2500)
            snippets.append(raw_text[start:end])

    if not snippets:
        return {"education": [], "field_resolution": {"education": []}}

    context = "\n\n---\n\n".join(snippets[:3])
    llm = get_fast_llm()
    prompt = RESUME_EDU_FALLBACK_PROMPT.format(context=context)

    try:
        result = llm.invoke([HumanMessage(content=prompt)])
        content = result.content.strip()
        if content.startswith("```"):
            content = content[content.index("\n") + 1:]
        if content.endswith("```"):
            content = content[:-3]
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            parsed = json.loads(content[start:end + 1])
        else:
            parsed = json.loads(content)
    except Exception as e:
        logger.error(f"Education fallback extraction failed: {e}")
        return {"education": [], "field_resolution": {"education": []}}

    education = parsed.get("education", [])
    field_resolution = parsed.get("field_resolution", {})
    
    # If LLM returned a single string instead of a list, wrap it
    if isinstance(education, str):
        education = [education]
        
    return {
        "education": education if isinstance(education, list) else [],
        "field_resolution": field_resolution if isinstance(field_resolution, dict) else {"education": []},
    }


def _extract_education_from_qualification_section(raw_text: str) -> list[str]:
    """Parse common Infracon qualification tables and generic education patterns without an API call."""
    results = []

    def add_unique(value: str) -> None:
        clean = re.sub(r"\s+", " ", value).strip(" ,.-")
        if clean and clean not in results:
            results.append(clean)

    # 1. Look for specific Infracon-style "QUALIFICATION DETAILS" section
    match = re.search(
        r"QUALIFICATION DETAILS(.*?)(?:COMPANIES DETAILS|DETAILED WORK DETAILS|EXPERIENCE|$)",
        raw_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    
    section = ""
    if match:
        section = match.group(1)
        # Clean up timestamps and URLs often found in Infracon exports
        section = re.sub(r"https?://\S+", " ", section)
        section = re.sub(r"\b\d{1,2}/\d{1,2}/\d{4},?\s+\d{1,2}:\d{2}\s*[APMapm]{2}\b", " ", section)
        section = re.sub(r"\s+", " ", section).strip()

    # 2. Extract from section using keywords
    if section:
        chunks = list(
            re.finditer(
                r"(Graduate/Degree|Post Graduate|Diploma|High School|Schooling)\s+(.*?)(?=Graduate/Degree|Post Graduate|Diploma|High School|Schooling|$)",
                section,
                flags=re.IGNORECASE,
            )
        )
        for chunk in chunks:
            level = chunk.group(1).strip()
            body = chunk.group(2).strip()
            year_match = re.search(r"((?:19|20)\d{2})", body)
            year = year_match.group(1) if year_match else None
            body_lower = body.lower()

            # Generic Level + Body combination
            value = f"{level} {body}".strip()
            add_unique(value)

    # 3. Broad search for common degree patterns if we didn't find much
    if len(results) < 1:
        # Common degree regex patterns
        degree_patterns = [
            r"\b(B\.?E\.?|B\.?Tech\.?|Bachelor of Technology|Bachelor of Engineering)\s+(?:in\s+)?([A-Za-z\s]{3,30})",
            r"\b(M\.?E\.?|M\.?Tech\.?|Master of Technology|Master of Engineering)\s+(?:in\s+)?([A-Za-z\s]{3,30})",
            r"\b(B\.?Sc\.?|Master of Science|M\.?Sc\.?)\s+(?:in\s+)?([A-Za-z\s]{3,30})",
            r"\b(B\.?A\.?|M\.?A\.?|Bachelor of Arts|Master of Arts)\s+(?:in\s+)?([A-Za-z\s]{3,30})",
            r"\b(MBA|M\.?B\.?A\.?|Master of Business Administration)\s+(?:in\s+)?([A-Za-z\s]{3,30})",
            r"\b(Ph\.?D\.?|Doctor of Philosophy)\b",
            r"\b(Diploma)\s+(?:in\s+)?([A-Za-z\s]{3,30})",
        ]
        
        for pattern in degree_patterns:
            for m in re.finditer(pattern, raw_text, flags=re.IGNORECASE):
                groups = m.groups()
                degree = groups[0]
                spec = groups[1] if len(groups) > 1 and groups[1] else ""
                val = f"{degree} {spec}".strip()
                # Find near university if possible (within 100 chars)
                context = raw_text[max(0, m.start() - 100):min(len(raw_text), m.end() + 100)]
                univ_match = re.search(r"(?:University|Institute|College) of ([A-Za-z\s]{3,50})", context, flags=re.IGNORECASE)
                if univ_match:
                    val += f", {univ_match.group(0)}"
                add_unique(val)

    return results


def _normalize_lookup_value(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def resolve_with_common_table_engine(category: str, raw_values: list[str], common_entries: list, db) -> dict:
    """
    Common Table Engine:
    1. Check exact/alias matches.
    2. Suggest normalized AI term for NO matches.
    3. Auto-insert/append to Common Table.
    """
    resolved_info = {}
    from app.models import CommonSkill, CommonEducation

    llm = get_fast_llm()

    for raw_value in raw_values:
        if not raw_value:
            continue
        
        if isinstance(raw_value, dict):
            vals = [str(v) for v in raw_value.values() if v]
            raw_value = ", ".join(vals)
        else:
            raw_value = str(raw_value)

        normalized_raw = _normalize_lookup_value(raw_value)
        if not normalized_raw:
            continue

        best_name = None
        best_score = 0
        for entry in common_entries:
            aliases = json.loads(entry.aliases) if entry.aliases else []
            candidates = [entry.name, *aliases]
            for candidate in candidates:
                normalized_candidate = _normalize_lookup_value(candidate)
                if not normalized_candidate:
                    continue
                score = 0
                if normalized_raw == normalized_candidate:
                    score = 100
                else:
                    raw_tokens = set(normalized_raw.split())
                    candidate_tokens = set(normalized_candidate.split())
                    if not raw_tokens or not candidate_tokens: continue
                    intersection = raw_tokens & candidate_tokens
                    # Strict token overlap (jaccard-ish)
                    overlap = len(intersection) / max(len(raw_tokens), len(candidate_tokens))
                    score = int(overlap * 100)

                if score > best_score:
                    best_score = score
                    best_name = entry.name

        # If we have a high-ish score but not exact, double check with a quick AI call
        if best_name and 70 <= best_score < 100:
            check_prompt = (
                f"Does the raw educational/skill value '{raw_value}' definitely refer to the exact same concept as "
                f"the catalog item '{best_name}'? Respond with ONLY 'YES' or 'NO'."
            )
            try:
                check_res = llm.invoke([HumanMessage(content=check_prompt)])
                if "YES" not in check_res.content.upper():
                    best_name = None # Rejected by AI
            except:
                pass

        if best_name and best_score >= 80:
            # Match Found!
            resolved_info[raw_value] = best_name
            # Append alias if new
            entry = next((e for e in common_entries if e.name == best_name), None)
            if entry:
                aliases = json.loads(entry.aliases) if entry.aliases else []
                if raw_value not in aliases:
                    aliases.append(raw_value)
                    entry.aliases = json.dumps(aliases)
                    db.flush()
        else:
            # NO Match -> AI normalizes
            prompt = RESUME_NORMALIZER_PROMPT.format(category=category, raw_value=raw_value)
            try:
                result = llm.invoke([HumanMessage(content=prompt)])
                normalized_key = result.content.strip()
                # Clean accidental quotes or code blocks
                if normalized_key.startswith("```"):
                    normalized_key = normalized_key.split("\n", 1)[-1].split("```")[0].strip()
                normalized_key = re.sub(r"[^a-z0-9_]", "", normalized_key.lower()).strip("_")
                if not normalized_key:
                    normalized_key = re.sub(r"[^a-z0-9]+", "_", raw_value.lower()).strip("_")
            except Exception as e:
                logger.warning(f"AI Normalization failed for '{raw_value}': {e}")
                normalized_key = re.sub(r"[^a-z0-9]+", "_", raw_value.lower()).strip("_")

            # Validate generated key doesn't clash with an existing one by chance
            entry = next((e for e in common_entries if e.name == normalized_key), None)
            if not entry:
                if category == "skills":
                    entry = CommonSkill(name=normalized_key, aliases=json.dumps([raw_value]))
                else:
                    level = _classify_education_level(raw_value)
                    entry = CommonEducation(name=normalized_key, aliases=json.dumps([raw_value]), level=level)
                db.add(entry)
                common_entries.append(entry)
            else:
                aliases = json.loads(entry.aliases) if entry.aliases else []
                if raw_value not in aliases:
                    aliases.append(raw_value)
                    entry.aliases = json.dumps(aliases)
            db.flush()
            resolved_info[raw_value] = normalized_key

    return resolved_info


_VALID_EDU_LEVELS = {"graduate", "postgraduate", "phd", "diploma", "highschool", "other"}


def _classify_education_level(raw_value: str) -> str:
    """Classify a human-readable education/degree string into a canonical level.
    Uses fast LLM. Called once at extraction time from the readable raw_value."""
    if not raw_value or not raw_value.strip():
        return "other"
    llm = get_fast_llm()
    prompt = (
        f"Classify this academic qualification into exactly one category.\n\n"
        f"Qualification: {raw_value}\n\n"
        f"Categories:\n"
        f"- graduate      : Bachelor's level (B.E., B.Tech, BCA, BSc, BA, BBA, AMIE, and equivalents)\n"
        f"- postgraduate  : Master's level (M.Tech, M.E., MSc, MBA, MCA, Post-Graduate Diploma after graduation)\n"
        f"- phd           : Doctorate (Ph.D., D.Sc., etc.)\n"
        f"- diploma       : Polytechnic or after-10th diploma (NOT post-grad diploma)\n"
        f"- highschool    : Class X, Class XII, Secondary / Senior Secondary\n"
        f"- other         : If none of the above applies\n\n"
        f"Reply with ONLY the single category word. No explanation."
    )
    prompt = RESUME_EDU_CLASSIFIER_PROMPT.format(raw_value=raw_value)
    try:
        result = llm.invoke([HumanMessage(content=prompt)])
        level = result.content.strip().lower().split()[0]
        return level if level in _VALID_EDU_LEVELS else "other"
    except Exception as e:
        logger.warning(f"Education level classification failed for '{raw_value}': {e}")
        return "other"


def post_process(state: ExtractionState) -> dict:
    """Post-process extracted data: handle field resolution and common table updates."""
    data = state.get("final_data") or state.get("extracted_data", {})
    raw_text = state["raw_text"]
    doc_type = state.get("doc_type", "resume")

    if not data.get("education"):
        local_education = _extract_education_from_qualification_section(raw_text)
        if local_education:
            data["education"] = local_education
        else:
            edu_fallback = _extract_education_with_targeted_llm(raw_text)
            if edu_fallback.get("education"):
                data["education"] = edu_fallback["education"]
                field_res = data.get("field_resolution", {}) or {}
                if not field_res.get("education"):
                    field_res["education"] = edu_fallback.get("field_resolution", {}).get("education", [])
                    data["field_resolution"] = field_res

    # 1. Experience Calculation (Existing logic)
    if data.get("total_years_experience", 0) <= 0:
        experience = data.get("experience", [])
        calculated = _calculate_experience_from_dates(experience)
        if calculated > 0:
            data["total_years_experience"] = calculated
        else:
            raw = raw_text[:10000].lower()
            # Stricter regex: avoid picking up years from education titles or single digits
            patterns = [
                r'total\s+professional\s+experience[:\s]+(\d+(?:\.\d+)?)\s*years?',
                r'(\d+(?:\.\d+)?)\s+years?\s+of\s+professional\s+experience',
                r'professional\s+experience[:\s]+(\d+(?:\.\d+)?)\s*years?',
            ]
            for pattern in patterns:
                match = re.search(pattern, raw)
                if match:
                    years = float(match.group(1))
                    if 1 <= years <= 60:
                        data["total_years_experience"] = years
                        break

    # 2. Field Resolution & Common Table Persistence
    field_res = data.get("field_resolution", {})
    db = SessionLocal()
    
    try:
        # Standardize Skills using Common Table Engine
        raw_skills = data.get("skills", [])
        if raw_skills:
            existing_skills = db.query(CommonSkill).all()
            mapped_skills = resolve_with_common_table_engine("skills", raw_skills, existing_skills, db)
            data["standardized_skills"] = list(set(mapped_skills.values()))
            
            # Update field_resolution mapping if needed
            field_res = data.get("field_resolution", {}) or {}
            skills_source = field_res.get("skills_source", {}) if isinstance(field_res, dict) else {}
            for original_raw, clean_slug in mapped_skills.items():
                if clean_slug not in skills_source:
                    skills_source[clean_slug] = original_raw
            field_res["skills_source"] = skills_source
            data["field_resolution"] = field_res

        # Standardize Education using Common Table Engine
        raw_edu = data.get("education", [])
        if raw_edu:
            existing_edu = db.query(CommonEducation).all()
            mapped_edu = resolve_with_common_table_engine("education", raw_edu, existing_edu, db)
            data["standardized_education"] = list(set(mapped_edu.values()))
            
            # Update field_resolution mapping if needed
            field_res = data.get("field_resolution", {}) or {}
            edu_source = field_res.get("education_source", {}) if isinstance(field_res, dict) else {}
            for original_raw, clean_slug in mapped_edu.items():
                if clean_slug not in edu_source:
                    edu_source[clean_slug] = original_raw
            field_res["education_source"] = edu_source
            data["field_resolution"] = field_res
        
        # 3. Deterministic Derived Profile Overwrite/Merge (Since LLM might hallucinate counts)
        # We allow LLM derived fields but compute flags using our trusted engine if doc_type == "resume"
        if doc_type == "resume":
            trusted_profile = compute_derived_profile(data)
            llm_profile = data.get("derived_profile", {})
            # Merge dictionary (using trusted profile where confident, retaining LLM extracted otherwise if custom fields exist)
            if isinstance(llm_profile, dict):
                llm_profile.update(trusted_profile)
                data["derived_profile"] = llm_profile
            else:
                data["derived_profile"] = trusted_profile
            
        db.commit()
        
    except Exception as e:
        logger.error(f"Post-process resolution failed: {e}")
        db.rollback()
    finally:
        db.close()

    return {"final_data": data}


# --- Build Graph ---

def _set_final_data(state: ExtractionState) -> dict:
    """Copy extracted_data to final_data when no issues found."""
    return {"final_data": state["extracted_data"]}


def build_extraction_agent_graph() -> StateGraph:
    graph = StateGraph(ExtractionState)

    graph.add_node("build_structure", build_structure)
    graph.add_node("deep_extract", deep_extract)
    graph.add_node("self_verify", self_verify)
    graph.add_node("fix_issues", fix_issues)
    graph.add_node("set_final_data", _set_final_data)
    graph.add_node("post_process", post_process)

    graph.set_entry_point("build_structure")
    graph.add_edge("build_structure", "deep_extract")
    graph.add_edge("deep_extract", "self_verify")
    graph.add_conditional_edges("self_verify", has_issues, {
        "fix_issues": "fix_issues",
        END: "set_final_data",
    })
    graph.add_edge("fix_issues", "post_process")
    graph.add_edge("set_final_data", "post_process")
    graph.add_edge("post_process", END)

    return graph.compile()


extraction_agent = build_extraction_agent_graph()

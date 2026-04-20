from __future__ import annotations
import json
import logging
import numpy as np
from typing import Optional
from sqlalchemy.orm import Session

from app.models import Resume, Tender, MatchResult
from app.schemas import (
    ResumeParseResult,
    RequiredRole,
    MatchResultItem,
    MatchResponse,
    ScoreBreakdown,
    RoleRequirements,
)
from app.services.embedding import embed_texts, query_similar_resumes
from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain-specific synonym groups for construction / IT terms
# Each inner list is a group of synonyms. Matching is case-insensitive.
# ---------------------------------------------------------------------------
SYNONYM_GROUPS: list[list[str]] = [
    ["roads", "highways", "road construction", "highway engineering"],
    ["it domain expertise", "it project management", "information technology"],
    ["parks", "landscaping", "garden design"],
    ["water supply", "water management", "water distribution"],
    ["sewerage", "waste water", "sanitation"],
    ["drainage", "storm water", "flood management"],
    ["bridge engineering", "structural engineering", "bridge design"],
    ["tunnel design", "underground construction"],
    ["gis", "geographic information system", "geospatial"],
    ["ai", "artificial intelligence", "machine learning", "ml"],
    ["cloud computing", "cloud platforms", "aws", "azure"],
    ["project management", "project planning", "pmo"],
    ["construction supervision", "site supervision", "quality control"],
    ["civil engineering", "infrastructure engineering"],
    ["survey", "surveying", "land survey"],
    ["dpr", "detailed project report", "feasibility report"],
    ["railway", "railway engineering", "track work", "permanent way", "ir", "rvnl", "ircon", "dfccil", "railway bridge", "railway sector", "indian railways"],
    ["solar", "pv", "photovoltaic", "solar power", "solar energy", "solar farm", "renewable energy"],
    ["power", "electrical engineering", "substation", "transmission line", "power distribution"],
]

# Build a lookup: lowered term -> frozenset of all synonyms in that group
_synonym_lookup: dict[str, frozenset[str]] = {}
for _group in SYNONYM_GROUPS:
    _fset = frozenset(t.lower().strip() for t in _group)
    for _term in _fset:
        _synonym_lookup[_term] = _fset


def _are_synonyms(a: str, b: str) -> bool:
    """Return True if *a* and *b* belong to the same synonym group."""
    a_low = a.lower().strip()
    b_low = b.lower().strip()
    group = _synonym_lookup.get(a_low)
    if group and b_low in group:
        return True
    return False


def _synonym_match_score(required: str, resume_items: set[str]) -> tuple[float | None, str | None]:
    """Check if *required* has a synonym in *resume_items*.

    Returns (0.9, matched_item) on hit, or (None, None) if no synonym found.
    """
    for res in resume_items:
        if _are_synonyms(required, res):
            return 0.9, res
    return None, None


# Cache for skill embeddings to minimize API calls
_skill_embedding_cache: dict[str, list[float]] = {}


async def _get_skill_embeddings(skills: list[str]) -> dict[str, list[float]]:
    """Get embeddings for skills, using cache to minimize API calls."""
    uncached = [s for s in skills if s.lower().strip() not in _skill_embedding_cache]
    if uncached:
        try:
            embeddings = await embed_texts(uncached)
            for skill, emb in zip(uncached, embeddings):
                _skill_embedding_cache[skill.lower().strip()] = emb
        except Exception as e:
            logger.error(f"Failed to embed skills: {e}")
    return {s.lower().strip(): _skill_embedding_cache.get(s.lower().strip(), []) for s in skills}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b:
        return 0.0
    a_arr = np.array(a)
    b_arr = np.array(b)
    dot = np.dot(a_arr, b_arr)
    norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    return float(dot / norm) if norm > 0 else 0.0


def _calculate_experience_score(resume_years: float, required_years: float) -> float:
    """Score experience match (0-10 points).

    Full marks if candidate meets or exceeds requirement.
    Proportional marks if under requirement.
    """
    if required_years <= 0:
        return 10.0

    ratio = resume_years / required_years
    if ratio >= 1.0:
        return 10.0
    return ratio * 10.0


def _calculate_skills_score_sync(resume_skills: list[str], required_skills: list[str],
                                  semantic_matches: dict[str, float] | None = None) -> float:
    """Score skills overlap (0-35 points).

    Uses exact match + fuzzy substring + semantic similarity.
    semantic_matches: dict mapping required_skill -> best similarity score from embeddings
    """
    if not required_skills:
        return 35.0

    resume_skills_lower = {s.lower().strip() for s in resume_skills}
    required_skills_lower = [s.lower().strip() for s in required_skills]

    total_matched = 0.0
    used_resume_skills = set()

    for req_skill in required_skills_lower:
        match_found = False
        
        # Exact match
        if req_skill in resume_skills_lower and req_skill not in used_resume_skills:
            total_matched += 1.0
            used_resume_skills.add(req_skill)
            continue

        # Domain synonym match
        syn_score, matched_res = _synonym_match_score(req_skill, resume_skills_lower - used_resume_skills)
        if syn_score is not None:
            total_matched += syn_score
            used_resume_skills.add(matched_res)
            continue

        # Fuzzy substring match
        for res_skill in (resume_skills_lower - used_resume_skills):
            if req_skill in res_skill or res_skill in req_skill:
                total_matched += 0.8
                used_resume_skills.add(res_skill)
                match_found = True
                break
        
        if match_found:
            continue

        # Word overlap (e.g., "machine learning" and "ml/machine learning")
        req_words = set(req_skill.split())
        for res_skill in (resume_skills_lower - used_resume_skills):
            res_words = set(res_skill.split())
            overlap = req_words & res_words
            # Require >50% word overlap to count
            if overlap and len(overlap) / len(req_words) > 0.5:
                total_matched += 0.6
                used_resume_skills.add(res_skill)
                match_found = True
                break

        if match_found:
            continue

        # Semantic similarity fallback (from embeddings) — lowered thresholds
        if semantic_matches:
            sim = semantic_matches.get(req_skill, 0)
            if sim >= 0.82:
                total_matched += 0.9
            elif sim >= 0.65:
                total_matched += 0.7
            elif sim >= 0.55:
                total_matched += 0.4

    ratio = min(total_matched / len(required_skills_lower), 1.0)
    return ratio * 35.0


def _calculate_domain_score(resume_domains: list[str], required_domains: list[str],
                            semantic_matches: dict[str, float] | None = None) -> float:
    """Score domain match (0-25 points)."""
    if not required_domains:
        return 25.0

    resume_domains_lower = {d.lower().strip() for d in resume_domains}
    required_domains_lower = [d.lower().strip() for d in required_domains]

    matched = 0.0
    used_resume_domains = set()
    
    for req_domain in required_domains_lower:
        if req_domain in resume_domains_lower and req_domain not in used_resume_domains:
            matched += 1.0
            used_resume_domains.add(req_domain)
            continue
            
        # Domain synonym match
        syn_score, matched_res = _synonym_match_score(req_domain, resume_domains_lower - used_resume_domains)
        if syn_score is not None:
            matched += syn_score
            used_resume_domains.add(matched_res)
            continue
            
        # Fuzzy match
        found = False
        for res_domain in (resume_domains_lower - used_resume_domains):
            if req_domain in res_domain or res_domain in req_domain:
                matched += 0.8
                used_resume_domains.add(res_domain)
                found = True
                break
                
        # Semantic fallback — lowered thresholds
        if not found and semantic_matches:
            sim = semantic_matches.get(req_domain, 0)
            if sim >= 0.70:
                matched += 0.8
            elif sim >= 0.55:
                matched += 0.5

    ratio = min(matched / len(required_domains_lower), 1.0)
    return ratio * 25.0


def _calculate_certification_score(
    resume_certs: list[str], required_certs: list[str]
) -> float:
    """Score certification match (0-15 points)."""
    if not required_certs:
        return 15.0

    resume_certs_lower = {c.lower().strip() for c in resume_certs}
    required_certs_lower = {c.lower().strip() for c in required_certs}

    matched = 0
    for req_cert in required_certs_lower:
        for res_cert in resume_certs_lower:
            if req_cert in res_cert or res_cert in req_cert:
                matched += 1
                break

    ratio = min(matched / len(required_certs_lower), 1.0)
    return ratio * 15.0


def _calculate_education_score(education: list[str]) -> float:
    """Score education level (0-15 points)."""
    education_text = " ".join(education).lower()

    if any(term in education_text for term in ["phd", "doctorate", "ph.d"]):
        return 15.0
    if any(term in education_text for term in ["master", "m.tech", "m.sc", "mba", "m.e.", "m.s."]):
        return 12.0
    if any(term in education_text for term in ["bachelor", "b.tech", "b.sc", "b.e.", "b.s.", "graduate"]):
        return 9.0
    if any(term in education_text for term in ["diploma", "associate"]):
        return 6.0

    return 4.0  # Default score for unrecognized education


def _compute_skill_matches(resume_skills: list[str], required_skills: list[str],
                           semantic_matches: dict[str, float] | None = None) -> tuple[list[str], list[str]]:
    """Return (matched_skills, missing_skills) from required list.

    Uses exact, substring, word overlap, and semantic similarity.
    """
    resume_lower = {s.lower().strip() for s in resume_skills}
    matched = []
    missing = []
    for req in required_skills:
        req_l = req.lower().strip()
        found = req_l in resume_lower
        # Domain synonym match
        if not found:
            found = _synonym_match_score(req_l, resume_lower) is not None
        if not found:
            for rs in resume_lower:
                if req_l in rs or rs in req_l:
                    found = True
                    break
        # Word overlap
        if not found:
            req_words = set(req_l.split())
            for rs in resume_lower:
                rs_words = set(rs.split())
                overlap = req_words & rs_words
                if overlap and len(overlap) / len(req_words) > 0.5:
                    found = True
                    break
        # Semantic similarity fallback — lowered threshold from 0.75 to 0.65
        if not found and semantic_matches:
            sim = semantic_matches.get(req_l, 0)
            if sim >= 0.65:
                found = True
        if found:
            matched.append(req)
        else:
            missing.append(req)
    return matched, missing


async def _compute_semantic_skill_matches(
    resume_skills: list[str], required_skills: list[str]
) -> dict[str, float]:
    """Compute best semantic similarity for each required skill against resume skills.

    Returns dict: {required_skill_lower: best_similarity_score}
    """
    if not resume_skills or not required_skills:
        return {}

    try:
        all_skills = list(set(s.lower().strip() for s in resume_skills + required_skills))
        emb_map = await _get_skill_embeddings(all_skills)

        result = {}
        for req in required_skills:
            req_l = req.lower().strip()
            req_emb = emb_map.get(req_l, [])
            if not req_emb:
                result[req_l] = 0.0
                continue
            best_sim = 0.0
            for res in resume_skills:
                res_l = res.lower().strip()
                res_emb = emb_map.get(res_l, [])
                if res_emb:
                    sim = _cosine_similarity(req_emb, res_emb)
                    best_sim = max(best_sim, sim)
            result[req_l] = best_sim
        return result
    except Exception as e:
        logger.error(f"Semantic skill matching failed: {e}")
        return {}


async def calculate_structured_score(
    resume_data: ResumeParseResult, role: RequiredRole
) -> tuple[float, ScoreBreakdown]:
    """Calculate the structured score for a resume against a role.

    Uses semantic similarity as fallback for skill/domain matching.
    Returns (total_score, breakdown) where total is 0-100.
    """
    # Compute semantic similarities for skills and domains
    skill_sims = await _compute_semantic_skill_matches(
        resume_data.skills, role.required_skills
    )
    domain_sims = await _compute_semantic_skill_matches(
        resume_data.domain_expertise, role.required_domain
    )

    exp_score = _calculate_experience_score(
        resume_data.total_years_experience, role.min_experience
    )
    skills_score = _calculate_skills_score_sync(
        resume_data.skills, role.required_skills, semantic_matches=skill_sims
    )
    domain_score = _calculate_domain_score(
        resume_data.domain_expertise, role.required_domain, semantic_matches=domain_sims
    )
    cert_score = _calculate_certification_score(
        resume_data.certifications, role.required_certifications
    )
    edu_score = _calculate_education_score(resume_data.education)

    total = exp_score + skills_score + domain_score + cert_score + edu_score

    breakdown = ScoreBreakdown(
        experience=round(exp_score, 2),
        skills=round(skills_score, 2),
        domain=round(domain_score, 2),
        certifications=round(cert_score, 2),
        education=round(edu_score, 2),
    )

    return total, breakdown


async def compute_skill_matches_with_semantics(
    resume_skills: list[str], required_skills: list[str]
) -> tuple[list[str], list[str]]:
    """Compute skill matches with semantic similarity fallback."""
    skill_sims = await _compute_semantic_skill_matches(resume_skills, required_skills)
    return _compute_skill_matches(resume_skills, required_skills, semantic_matches=skill_sims)


async def match_tender(tender_id: int, db: Session) -> list[MatchResponse]:
    """Run full matching for all roles in a tender.

    Returns ranked results per role.
    """
    tender = db.query(Tender).filter(Tender.id == tender_id).first()
    if not tender:
        raise ValueError(f"Tender {tender_id} not found")

    roles_data = json.loads(tender.required_roles)
    if not roles_data:
        return []

    # Clear previous match results for this tender
    db.query(MatchResult).filter(MatchResult.tender_id == tender_id).delete()
    db.commit()

    all_results = []

    for role_idx, role_data in enumerate(roles_data):
        role = RequiredRole(**role_data)

        # Build a text representation of the role for semantic search
        role_text = f"{role.role_title}. "
        if role.required_skills:
            role_text += f"Required skills: {', '.join(role.required_skills)}. "
        if role.min_experience > 0:
            role_text += f"Minimum {role.min_experience} years of experience required. "
        if role.required_domain:
            role_text += f"Domain expertise: {', '.join(role.required_domain)}. "
        if role.required_certifications:
            role_text += f"Certifications: {', '.join(role.required_certifications)}."

        # Phase 1: Semantic search
        try:
            role_embedding = await embed_texts([role_text])
            semantic_results = query_similar_resumes(
                role_embedding[0], n_results=settings.top_k_candidates
            )
        except Exception as e:
            logger.error(f"Semantic search failed for role {role.role_title}: {e}")
            semantic_results = {"ids": [[]], "distances": [[]], "metadatas": [[]]}

        # Phase 2: Structured scoring for each candidate
        role_matches = []

        if semantic_results["ids"] and semantic_results["ids"][0]:
            for resume_id_str, distance in zip(
                semantic_results["ids"][0], semantic_results["distances"][0]
            ):
                resume_id = int(resume_id_str)
                # Cosine distance to similarity: ChromaDB returns distance, similarity = 1 - distance
                semantic_similarity = max(0, 1 - distance)

                resume = db.query(Resume).filter(Resume.id == resume_id).first()
                if not resume:
                    continue

                try:
                    resume_parsed = json.loads(resume.parsed_data)
                    resume_data = ResumeParseResult(**resume_parsed)
                except Exception:
                    continue

                struct_score, breakdown = calculate_structured_score(resume_data, role)

                # Combined score
                sem_normalized = semantic_similarity * 100
                final = (
                    settings.semantic_weight * sem_normalized
                    + settings.structured_weight * struct_score
                )

                matched_skills, missing_skills = _compute_skill_matches(
                    resume_data.skills, role.required_skills
                )

                photo_url = f"/api/resumes/photo/{resume.photo_filename}" if resume.photo_filename else None
                designation = resume_data.experience[0].role if resume_data.experience else None

                match_item = MatchResultItem(
                    resume_id=resume_id,
                    candidate_name=resume.name,
                    role_title=role.role_title,
                    final_score=round(final, 2),
                    semantic_score=round(sem_normalized, 2),
                    structured_score=round(struct_score, 2),
                    score_breakdown=breakdown,
                    matched_skills=matched_skills,
                    missing_skills=missing_skills,
                    experience_years=resume_data.total_years_experience,
                    designation=designation,
                    photo_url=photo_url,
                )
                role_matches.append(match_item)

                # Persist to database
                db_match = MatchResult(
                    tender_id=tender_id,
                    role_title=role.role_title,
                    resume_id=resume_id,
                    semantic_score=round(sem_normalized, 2),
                    structured_score=round(struct_score, 2),
                    final_score=round(final, 2),
                    score_breakdown=json.dumps(breakdown.model_dump()),
                )
                db.add(db_match)

        # Deduplicate: keep only best score per candidate name
        best_by_name: dict[str, MatchResultItem] = {}
        for item in role_matches:
            if item.candidate_name not in best_by_name or item.final_score > best_by_name[item.candidate_name].final_score:
                best_by_name[item.candidate_name] = item

        # Filter by minimum score and sort descending
        role_matches = [
            item for item in best_by_name.values()
            if item.final_score >= settings.min_match_score
        ]
        role_matches.sort(key=lambda x: x.final_score, reverse=True)

        role_reqs = RoleRequirements(
            min_experience=role.min_experience,
            required_skills=role.required_skills,
            required_certifications=role.required_certifications,
            required_domain=role.required_domain,
        )

        all_results.append(
            MatchResponse(
                tender_id=tender_id,
                project_name=tender.project_name,
                role_title=role.role_title,
                role_requirements=role_reqs,
                results=role_matches,
            )
        )

    db.commit()
    return all_results

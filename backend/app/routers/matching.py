"""Matching router using the LLM-as-judge matching agent."""
import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Tender, MatchResult, Resume
from app.schemas import (
    MatchResponse, MatchResultItem, ScoreBreakdown, MatchSummary,
    RoleRequirements, RequiredRole, ScoringCriterion,
)
from app.agents.matching_agent import determine_criteria, pre_filter, evaluate_candidates, rank_and_explain
from app.services.structured_scorer import calculate_structured_score, _compute_skill_matches, compute_skill_matches_with_semantics
from app.services.sql_prefilter import build_sql_shortlist
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/match", tags=["matching"])


@router.post("/{tender_id}", response_model=list)
async def run_matching(tender_id: int, db: Session = Depends(get_db)):
    """Run agentic matching for all roles in a tender."""
    tender = db.query(Tender).filter(Tender.id == tender_id).first()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
    if tender.parse_status != "success":
        raise HTTPException(status_code=400, detail="Tender was not parsed successfully")

    resume_count = db.query(Resume).count()
    if resume_count == 0:
        raise HTTPException(status_code=400, detail="No resumes in database.")

    roles_data = json.loads(tender.required_roles) if tender.required_roles else []
    if not roles_data:
        return []

    tender_parsed = json.loads(tender.parsed_data) if tender.parsed_data else {}

    # Clear previous results
    db.query(MatchResult).filter(MatchResult.tender_id == tender_id).delete()
    db.commit()

    all_results = []

    for role_data in roles_data:
        role = RequiredRole(**role_data)

        try:
            # Step 0: SQL Prefilter
            logger.info(f"Running SQL prefilter for role: {role.role_title}")
            sql_candidate_ids = build_sql_shortlist(db, role_data)
            logger.info(f"SQL prefilter yielded {len(sql_candidate_ids)} candidates")

            # Run matching agent
            state = {
                "tender_id": tender_id,
                "tender_data": tender_parsed,
                "role": role_data,
                "candidate_resumes": [],
                "scoring_criteria": [],
                "evaluations": [],
                "rankings": [],
                "sql_shortlist": sql_candidate_ids,
                "error": None,
            }

            # Wait, rather than loading ALL resumes and filtering later,
            # we will only load the ones pre-filtered plus whatever the fallback loads.
            # But the fallback logic is in `pre_filter(state)` node.
            # It's better to just build the lookup for all successful resumes to avoid multiple trips. 
            # (In production with 10kumes this is bad, but keeping original flow mostly intact).
            all_resumes = db.query(Resume).filter(Resume.parse_status == "success").all()
            resume_lookup = {}
            for r in all_resumes:
                parsed = json.loads(r.parsed_data) if r.parsed_data else {}
                resume_lookup[r.id] = {
                    "resume_id": r.id,
                    "parsed_data": parsed,
                    "name": r.name,
                    "photo_filename": r.photo_filename,
                }

            # Run agent nodes manually so we can inject data between steps
            # Step 1: Determine criteria
            state.update(determine_criteria(state))

            # Step 2: Pre-filter (vector search for candidate IDs)
            state.update(pre_filter(state))

            # Step 3: Inject full resume data for candidates
            enriched = []
            for c in state.get("candidate_resumes", []):
                rid = c["resume_id"]
                if rid in resume_lookup:
                    enriched.append(resume_lookup[rid])
            state["candidate_resumes"] = enriched

            # Step 4: Evaluate candidates with LLM
            state.update(evaluate_candidates(state))

            # Step 5: Rank
            state.update(rank_and_explain(state))

            result = state

            # Process rankings
            scoring_criteria = [
                ScoringCriterion(**c) for c in result.get("scoring_criteria", [])
            ]

            role_matches = []
            for eval_item in result.get("rankings", []):
                rid = eval_item.get("resume_id")
                resume_info = resume_lookup.get(rid, {})
                parsed = resume_info.get("parsed_data", {})
                exp_list = parsed.get("experience", [])
                designation = exp_list[0].get("role") if exp_list else None
                photo_fn = resume_info.get("photo_filename")
                photo_url = f"/api/resumes/photo/{photo_fn}" if photo_fn else None

                llm_score = eval_item.get("overall_score", 0)
                strengths = eval_item.get("strengths", [])
                concerns = eval_item.get("concerns", [])
                explanation = eval_item.get("explanation", "")

                # Hybrid: compute V1 structured score too (with semantic matching)
                from app.schemas import ResumeParseResult
                try:
                    resume_parsed = ResumeParseResult(**parsed)
                    struct_score, breakdown = await calculate_structured_score(resume_parsed, role)
                    matched_skills, missing_skills = await compute_skill_matches_with_semantics(
                        resume_parsed.skills, role.required_skills
                    )
                except Exception as exc:
                    logger.error(f"Structured scoring failed for resume {rid}: {exc}", exc_info=True)
                    struct_score = 0
                    breakdown = ScoreBreakdown()
                    matched_skills = []
                    missing_skills = list(role.required_skills)

                # Hybrid final: 50% structured + 50% LLM
                hybrid_final = round(0.5 * struct_score + 0.5 * llm_score, 2)

                match_item = MatchResultItem(
                    resume_id=rid,
                    candidate_name=eval_item.get("candidate_name", "Unknown"),
                    role_title=role.role_title,
                    final_score=hybrid_final,
                    semantic_score=0,
                    structured_score=struct_score,
                    score_breakdown=breakdown,
                    matched_skills=matched_skills,
                    missing_skills=missing_skills,
                    experience_years=parsed.get("total_years_experience", 0),
                    designation=designation,
                    photo_url=photo_url,
                    llm_score=llm_score,
                    llm_explanation=explanation,
                    strengths=strengths,
                    concerns=concerns,
                )
                role_matches.append(match_item)

                # Persist
                db_match = MatchResult(
                    tender_id=tender_id,
                    role_title=role.role_title,
                    resume_id=rid,
                    final_score=hybrid_final,
                    structured_score=round(struct_score, 2),
                    llm_score=llm_score,
                    llm_explanation=explanation,
                    strengths=json.dumps(strengths),
                    concerns=json.dumps(concerns),
                    scoring_criteria=json.dumps([c.model_dump() for c in scoring_criteria]),
                    score_breakdown=json.dumps(breakdown.model_dump()),
                )
                db.add(db_match)

            # Filter by min score
            role_matches = [m for m in role_matches if m.final_score >= settings.min_match_score]

            role_reqs = RoleRequirements(
                min_experience=role.min_experience,
                required_skills=role.required_skills,
                required_certifications=role.required_certifications,
                required_domain=role.required_domain,
            )

            all_results.append(MatchResponse(
                tender_id=tender_id,
                project_name=tender.project_name,
                role_title=role.role_title,
                role_requirements=role_reqs,
                scoring_criteria=scoring_criteria,
                results=role_matches,
            ))

        except Exception as e:
            logger.error(f"Matching agent failed for role {role.role_title}: {e}")
            all_results.append(MatchResponse(
                tender_id=tender_id,
                project_name=tender.project_name,
                role_title=role.role_title,
                role_requirements=RoleRequirements(**role_data),
                results=[],
            ))

    db.commit()
    return all_results


@router.get("/{tender_id}/results")
async def get_match_results(
    tender_id: int,
    role: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Get stored match results for a tender."""
    tender = db.query(Tender).filter(Tender.id == tender_id).first()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    query = db.query(MatchResult).filter(MatchResult.tender_id == tender_id)
    if role:
        query = query.filter(MatchResult.role_title == role)

    records = query.order_by(MatchResult.role_title, MatchResult.final_score.desc()).all()
    if not records:
        raise HTTPException(status_code=404, detail="No match results found.")

    roles_data = json.loads(tender.required_roles) if tender.required_roles else []
    roles_by_title = {r.get("role_title"): r for r in roles_data}

    roles_dict = {}
    for rec in records:
        if rec.role_title not in roles_dict:
            roles_dict[rec.role_title] = []

        resume = db.query(Resume).filter(Resume.id == rec.resume_id).first()
        name = resume.name if resume else "Unknown"
        designation = None
        exp_years = 0.0
        photo_url = None
        if resume:
            parsed = json.loads(resume.parsed_data) if resume.parsed_data else {}
            exp = parsed.get("experience", [])
            designation = exp[0].get("role") if exp else None
            exp_years = parsed.get("total_years_experience", 0)
            if resume.photo_filename:
                photo_url = f"/api/resumes/photo/{resume.photo_filename}"

        strengths = json.loads(rec.strengths) if rec.strengths else []
        concerns = json.loads(rec.concerns) if rec.concerns else []

        # Read stored breakdown or recompute
        try:
            bd_data = json.loads(rec.score_breakdown) if rec.score_breakdown else {}
            breakdown = ScoreBreakdown(**bd_data) if bd_data else ScoreBreakdown()
        except Exception:
            breakdown = ScoreBreakdown()

        # Compute matched/missing skills from stored data (with semantic matching)
        matched_skills = []
        missing_skills = []
        if resume and parsed:
            try:
                from app.schemas import ResumeParseResult, RequiredRole as RR
                rd = roles_by_title.get(rec.role_title, {})
                if rd:
                    rp = ResumeParseResult(**parsed)
                    matched_skills, missing_skills = await compute_skill_matches_with_semantics(
                        rp.skills, rd.get("required_skills", [])
                    )
            except Exception:
                pass

        roles_dict[rec.role_title].append(MatchResultItem(
            resume_id=rec.resume_id,
            candidate_name=name,
            role_title=rec.role_title,
            final_score=rec.final_score,
            semantic_score=rec.semantic_score or 0,
            structured_score=rec.structured_score or 0,
            score_breakdown=breakdown,
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            experience_years=exp_years,
            designation=designation,
            photo_url=photo_url,
            llm_score=rec.llm_score,
            llm_explanation=rec.llm_explanation,
            strengths=strengths,
            concerns=concerns,
        ))

    response = []
    for role_title, results in roles_dict.items():
        # Deduplicate
        best = {}
        for item in results:
            if item.candidate_name not in best or item.final_score > best[item.candidate_name].final_score:
                best[item.candidate_name] = item
        deduped = sorted(best.values(), key=lambda x: x.final_score, reverse=True)
        deduped = [i for i in deduped if i.final_score >= settings.min_match_score]

        rd = roles_by_title.get(role_title, {})
        criteria_json = results[0].score_breakdown if results else ScoreBreakdown()

        response.append(MatchResponse(
            tender_id=tender_id,
            project_name=tender.project_name,
            role_title=role_title,
            role_requirements=RoleRequirements(**rd) if rd else None,
            results=deduped,
        ))

    return response


@router.get("", response_model=list)
async def list_match_summaries(db: Session = Depends(get_db)):
    """List tenders with match results."""
    tender_ids = db.query(MatchResult.tender_id).distinct().all()
    summaries = []
    for (tid,) in tender_ids:
        tender = db.query(Tender).filter(Tender.id == tid).first()
        if not tender:
            continue
        roles = db.query(MatchResult.role_title).filter(MatchResult.tender_id == tid).distinct().all()
        total = db.query(MatchResult).filter(MatchResult.tender_id == tid).count()
        summaries.append(MatchSummary(
            tender_id=tid,
            project_name=tender.project_name,
            roles=[r[0] for r in roles],
            total_matches=total,
            created_at=tender.created_at,
        ))
    return summaries

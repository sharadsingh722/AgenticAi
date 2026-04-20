"""LLM-as-judge matching agent using LangGraph.

Graph: determine_criteria → pre_filter → evaluate_candidates → rank_and_explain → END
"""
import json
import logging
import asyncio
from typing import Optional, List, Dict, TypedDict

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.services.llm import get_reasoning_llm
from app.services.embedding import embed_texts, query_similar_resumes
from app.config import settings
from app.prompts.matching_prompts import MATCHING_CRITERIA_PROMPT, MATCHING_EVALUATION_PROMPT

logger = logging.getLogger(__name__)


# --- State ---

class MatchingState(TypedDict):
    tender_id: int
    tender_data: Dict
    role: Dict
    candidate_resumes: List[Dict]  # [{resume_id, name, parsed_data, ...}]
    scoring_criteria: List[Dict]  # [{criterion, weight, description}]
    evaluations: List[Dict]
    rankings: List[Dict]
    sql_shortlist: List[int]
    error: Optional[str]


# --- Structured output models ---

class CriterionDef(BaseModel):
    criterion: str = Field(description="Name of the criterion")
    weight: float = Field(description="Weight 0.0-1.0, all weights should sum to 1.0")
    description: str = Field(description="What to evaluate for this criterion")


class CriteriaResponse(BaseModel):
    criteria: List[CriterionDef]
    reasoning: str = Field(description="Why these criteria matter for this role")


class CandidateEvaluation(BaseModel):
    overall_score: float = Field(description="Overall fit score 0-100")
    strengths: List[str] = Field(description="Top 3 strengths of this candidate")
    concerns: List[str] = Field(description="Top concerns or gaps")
    explanation: str = Field(description="2-3 sentence explanation of the match quality")


# --- Nodes ---

def determine_criteria(state: MatchingState) -> dict:
    """Dynamically determine scoring criteria based on tender + role context."""
    llm = get_reasoning_llm().with_structured_output(CriteriaResponse)
    role = state["role"]
    tender = state["tender_data"]

    prompt = MATCHING_CRITERIA_PROMPT.format(
        project_name=tender.get('project_name', 'Unknown'),
        client=tender.get('client', 'Unknown'),
        technologies=', '.join(tender.get('key_technologies', [])),
        role_title=role.get('role_title', 'Unknown'),
        min_experience=role.get('min_experience', 0),
        required_skills=', '.join(role.get('required_skills', [])),
        required_certifications=', '.join(role.get('required_certifications', [])),
        required_domain=', '.join(role.get('required_domain', [])),
        preferred_components=', '.join(role.get('preferred_components', [])),
        min_project_value_cr=role.get('min_project_value_cr', 0.0),
        client_type_preference=role.get('client_type_preference', 'None')
    )
    result = llm.invoke([HumanMessage(content=prompt)])

    return {
        "scoring_criteria": [c.model_dump() for c in result.criteria],
    }


def build_role_query_text(role: dict) -> str:
    """Combines role requirements into a comprehensive query text for vector search."""
    role_text = f"{role.get('role_title', '')}. "
    if role.get("required_skills"):
        role_text += f"Skills: {', '.join(role['required_skills'])}. "
    if role.get("required_domain"):
        role_text += f"Domain: {', '.join(role['required_domain'])}. "
    if role.get("required_certifications"):
        role_text += f"Certifications: {', '.join(role['required_certifications'])}. "
    if role.get("preferred_components"):
        role_text += f"Components: {', '.join(role['preferred_components'])}. "
    if role.get("min_project_value_cr"):
        role_text += f"Project Scale > {role['min_project_value_cr']} Cr. "
    if role.get("client_type_preference") and role.get("client_type_preference").lower() != "none":
        role_text += f"Client Type: {role['client_type_preference']}. "
    return role_text

def pre_filter(state: MatchingState) -> dict:
    """Use hybrid SQL + vector search to narrow candidates. Uses sync OpenAI client."""
    from openai import OpenAI
    from app.database import SessionLocal
    from app.models import Resume

    role = state["role"]
    sql_shortlist = state.get("sql_shortlist", [])

    # Fallback to recent successful resumes if SQL shortlist is empty
    if not sql_shortlist:
        db = SessionLocal()
        try:
            recent_resumes = db.query(Resume.id).filter(Resume.parse_status == "success").order_by(Resume.id.desc()).limit(100).all()
            sql_shortlist = [r[0] for r in recent_resumes]
        except Exception as e:
            logger.error(f"Fallback retrieval failed: {e}")
        finally:
            db.close()

    role_text = build_role_query_text(role)

    # Use sync OpenAI client to avoid async event loop issues in LangGraph
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.embeddings.create(
        model=settings.embedding_model,
        input=[role_text[:8000]],
    )
    embedding = response.data[0].embedding

    # Pre-filter vector search with a reasonable top_k since we will intersect
    # We query more from the vector DB to ensure intersection yields enough candidates
    results = query_similar_resumes(embedding, n_results=50)

    candidate_ids = []
    if results["ids"] and results["ids"][0]:
        vector_ids = [int(rid) for rid in results["ids"][0]]
        # Intersect vector results with SQL shortlist
        intersected = [rid for rid in vector_ids if rid in sql_shortlist]
        
        # Take the top N from the intersected results
        candidate_ids = intersected[:settings.top_k_candidates]

    return {"candidate_resumes": [{"resume_id": rid} for rid in candidate_ids]}


def evaluate_candidates(state: MatchingState) -> dict:
    """LLM-as-judge: evaluate each candidate against dynamic criteria."""
    llm = get_reasoning_llm().with_structured_output(CandidateEvaluation)
    role = state["role"]
    criteria = state["scoring_criteria"]
    candidates = state.get("candidate_resumes", [])

    # We need full resume data - this will be populated by the router before calling
    evaluations = []

    criteria_text = "\n".join([
        f"- {c['criterion']} (weight: {c['weight']:.0%}): {c['description']}"
        for c in criteria
    ])

    for candidate in candidates:
        parsed = candidate.get("parsed_data", {})
        if not parsed:
            continue

        name = parsed.get("name", "Unknown")
        skills = ", ".join(parsed.get("skills", [])[:20])
        exp = parsed.get("experience", [])
        exp_text = "\n".join([
            f"  - {e.get('role', '?')} at {e.get('company', '?')} ({e.get('duration', '?')})"
            for e in exp[:5]
        ])
        education = ", ".join(parsed.get("education", []))
        certs = ", ".join(parsed.get("certifications", []))
        domains = ", ".join(parsed.get("domain_expertise", []))
        years = parsed.get("total_years_experience", 0)

        prompt = MATCHING_EVALUATION_PROMPT.format(
            role_title=role.get('role_title'),
            min_experience=role.get('min_experience', 0),
            min_project_value_cr=role.get('min_project_value_cr', 0.0),
            client_type_preference=role.get('client_type_preference', 'None'),
            required_skills=', '.join(role.get('required_skills', [])),
            required_domain=', '.join(role.get('required_domain', [])),
            preferred_components=', '.join(role.get('preferred_components', [])),
            required_certifications=', '.join(role.get('required_certifications', [])),
            criteria_text=criteria_text,
            candidate_name=name,
            years_experience=years,
            domains=domains,
            skills=skills,
            certifications=certs,
            education=education,
            derived_profile=json.dumps(parsed.get("derived_profile", {})),
            experience_history=exp_text
        )

        try:
            result = llm.invoke([HumanMessage(content=prompt)])

            evaluations.append({
                "resume_id": candidate["resume_id"],
                "candidate_name": name,
                "overall_score": result.overall_score,
                "strengths": result.strengths,
                "concerns": result.concerns,
                "explanation": result.explanation,
            })
        except Exception as e:
            logger.error(f"Evaluation failed for {name}: {e}")

    return {"evaluations": evaluations}


def rank_and_explain(state: MatchingState) -> dict:
    """Sort by score and generate summary."""
    evaluations = state.get("evaluations", [])
    ranked = sorted(evaluations, key=lambda x: x.get("overall_score", 0), reverse=True)
    return {"rankings": ranked}


# --- Build Graph ---

def build_matching_agent_graph() -> StateGraph:
    graph = StateGraph(MatchingState)

    graph.add_node("determine_criteria", determine_criteria)
    graph.add_node("pre_filter", pre_filter)
    graph.add_node("evaluate_candidates", evaluate_candidates)
    graph.add_node("rank_and_explain", rank_and_explain)

    graph.set_entry_point("determine_criteria")
    graph.add_edge("determine_criteria", "pre_filter")
    graph.add_edge("pre_filter", "evaluate_candidates")
    graph.add_edge("evaluate_candidates", "rank_and_explain")
    graph.add_edge("rank_and_explain", END)

    return graph.compile()


matching_agent = build_matching_agent_graph()

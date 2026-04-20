"""Vector search tools for the chat agent."""
import asyncio
import json
from typing import Optional
from langchain_core.tools import tool

from app.services.embedding import embed_texts, query_similar_resumes
from app.database import SessionLocal
from app.models import Resume, Tender


@tool
def search_resumes(query: str) -> str:
    """Search resumes by semantic similarity. Use for natural language queries like 'find candidates with drone experience' or 'engineers with GIS skills'."""
    async def _run():
        embeddings = await embed_texts([query])
        results = query_similar_resumes(embeddings[0], n_results=10)
        if not results["ids"] or not results["ids"][0]:
            return "No matching resumes found."

        db = SessionLocal()
        try:
            output = []
            for rid_str, dist in zip(results["ids"][0], results["distances"][0]):
                resume = db.query(Resume).filter(Resume.id == int(rid_str)).first()
                if not resume:
                    continue
                similarity = max(0, 1 - dist)
                parsed = json.loads(resume.parsed_data) if resume.parsed_data else {}
                exp = parsed.get("experience", [])
                current_role = exp[0].get("role", "N/A") if exp else "N/A"
                output.append(
                    f"- **{resume.name}** (ID:{resume.id}) | {current_role} | "
                    f"{resume.total_years_experience} yrs | "
                    f"Skills: {', '.join(json.loads(resume.skills)[:8])} | "
                    f"Relevance: {similarity:.0%}"
                )
            return "\n".join(output) if output else "No matching resumes found."
        finally:
            db.close()

    return asyncio.run(_run())


@tool
def search_tenders(query: str) -> str:
    """Search tenders/RFPs by keyword. Use for queries like 'road monitoring tenders' or 'IT projects in Bihar'."""
    db = SessionLocal()
    try:
        tenders = db.query(Tender).all()
        results = []
        query_lower = query.lower()
        for t in tenders:
            text = f"{t.project_name} {t.client or ''} {t.raw_text[:500]}".lower()
            if any(word in text for word in query_lower.split()):
                roles = json.loads(t.required_roles) if t.required_roles else []
                techs = json.loads(t.key_technologies) if t.key_technologies else []
                results.append(
                    f"- **TND-{t.id:04d}** | {t.project_name[:80]} | "
                    f"{t.client or 'N/A'} | {len(roles)} roles | "
                    f"Tech: {', '.join(techs[:5])}"
                )
        return "\n".join(results) if results else "No matching tenders found."
    finally:
        db.close()

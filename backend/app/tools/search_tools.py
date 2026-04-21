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
                photo_url = f"/api/resumes/photo/{resume.photo_filename}" if resume.photo_filename else ""
                output.append(
                    f"- **{resume.name}** (ID:{resume.id}) | {current_role} | "
                    f"{resume.total_years_experience} yrs | "
                    f"Photo: {photo_url} | "
                    f"Skills: {', '.join(json.loads(resume.skills)[:8])} | "
                    f"Relevance: {similarity:.0%}"
                )
            return "\n".join(output) if output else "No matching resumes found."
        finally:
            db.close()

    return asyncio.run(_run())


@tool
def search_tenders(query: str) -> str:
    """Search tenders/RFPs by semantic similarity. Use for natural language queries like 'infrastructure projects' or 'IT projects in Bihar'."""
    async def _run():
        embeddings = await embed_texts([query])
        from app.services.embedding import query_similar_tenders
        results = query_similar_tenders(embeddings[0], n_results=10)
        
        if not results["ids"] or not results["ids"][0]:
            return "No matching tenders found."

        db = SessionLocal()
        try:
            output = []
            for tid_str, dist in zip(results["ids"][0], results["distances"][0]):
                tender = db.query(Tender).filter(Tender.id == int(tid_str)).first()
                if not tender:
                    continue
                similarity = max(0, 1 - dist)
                roles = json.loads(tender.required_roles) if tender.required_roles else []
                techs = json.loads(tender.key_technologies) if tender.key_technologies else []
                output.append(
                    f"- **TND-{tender.id:04d}** | {tender.project_name[:80]} | "
                    f"{tender.client or 'N/A'} | {len(roles)} roles | "
                    f"Tech: {', '.join(techs[:5])} | Relevance: {similarity:.0%}"
                )
            return "\n".join(output) if output else "No matching tenders found."
        finally:
            db.close()

    return asyncio.run(_run())

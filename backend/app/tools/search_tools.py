"""Vector search tools for the chat agent."""
import asyncio
import json
from typing import Optional
from langchain_core.tools import tool
from sqlalchemy import case

from app.services.embedding import embed_texts, query_similar_resumes
from app.database import SessionLocal
from app.models import Resume, Tender

DEFAULT_RESULT_LIMIT = 5


def _build_paginated_text_response(items: list[str], *, label: str, limit: int = DEFAULT_RESULT_LIMIT, offset: int = 0) -> str:
    safe_limit = max(1, min(int(limit or DEFAULT_RESULT_LIMIT), 50))
    safe_offset = max(0, int(offset or 0))
    total = len(items)
    page = items[safe_offset:safe_offset + safe_limit]

    lines = [f"Total matching {label}: {total}"]
    if not page:
        lines.append(f"Showing 0 of {total} result(s). No more results remain for offset {safe_offset}.")
        return "\n".join(lines)

    start_index = safe_offset + 1
    end_index = safe_offset + len(page)
    lines.append(f"Showing {len(page)} of {total} result(s) ({start_index}-{end_index}).")
    lines.extend(page)

    remaining = max(0, total - end_index)
    if remaining > 0:
        lines.append(
            f"{remaining} more result(s) remain. Call this tool again with offset={end_index} "
            f"and limit={DEFAULT_RESULT_LIMIT} for the next page, or limit={remaining} to fetch the rest."
        )
    return "\n".join(lines)


@tool
def search_resumes(query: str, limit: int = DEFAULT_RESULT_LIMIT, offset: int = 0) -> str:
    """Search resumes by semantic similarity. Use limit/offset for pagination."""
    async def _run():
        embeddings = await embed_texts([query])
        results = query_similar_resumes(embeddings[0], n_results=50)
        if not results["ids"] or not results["ids"][0]:
            return "No matching resumes found."

        db = SessionLocal()
        try:
            ranked_ids = [int(rid) for rid in results["ids"][0]]
            distance_by_id = {
                int(rid): dist for rid, dist in zip(results["ids"][0], results["distances"][0])
            }
            order_by_rank = case(
                {rid: idx for idx, rid in enumerate(ranked_ids)},
                value=Resume.id,
            )
            resumes = (
                db.query(Resume)
                .filter(Resume.id.in_(ranked_ids))
                .order_by(order_by_rank)
                .all()
            )
            output = []
            for resume in resumes:
                dist = distance_by_id.get(resume.id)
                if dist is None:
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
            if not output:
                return "No matching resumes found."
            return _build_paginated_text_response(output, label="resumes", limit=limit, offset=offset)
        finally:
            db.close()

    return asyncio.run(_run())


@tool
def search_tenders(query: str, limit: int = DEFAULT_RESULT_LIMIT, offset: int = 0) -> str:
    """Search tenders/RFPs by semantic similarity. Use limit/offset for pagination."""
    async def _run():
        embeddings = await embed_texts([query])
        from app.services.embedding import query_similar_tenders
        results = query_similar_tenders(embeddings[0], n_results=50)
        
        if not results["ids"] or not results["ids"][0]:
            return "No matching tenders found."

        db = SessionLocal()
        try:
            ranked_ids = [int(tid) for tid in results["ids"][0]]
            distance_by_id = {
                int(tid): dist for tid, dist in zip(results["ids"][0], results["distances"][0])
            }
            order_by_rank = case(
                {tid: idx for idx, tid in enumerate(ranked_ids)},
                value=Tender.id,
            )
            tenders = (
                db.query(Tender)
                .filter(Tender.id.in_(ranked_ids))
                .order_by(order_by_rank)
                .all()
            )
            output = []
            for tender in tenders:
                dist = distance_by_id.get(tender.id)
                if dist is None:
                    continue
                similarity = max(0, 1 - dist)
                roles = json.loads(tender.required_roles) if tender.required_roles else []
                techs = json.loads(tender.key_technologies) if tender.key_technologies else []
                output.append(
                    f"- **TND-{tender.id:04d}** | {tender.project_name[:80]} | "
                    f"{tender.client or 'N/A'} | {len(roles)} roles | "
                    f"Tech: {', '.join(techs[:5])} | Relevance: {similarity:.0%}"
                )
            if not output:
                return "No matching tenders found."
            return _build_paginated_text_response(output, label="tenders", limit=limit, offset=offset)
        finally:
            db.close()

    return asyncio.run(_run())

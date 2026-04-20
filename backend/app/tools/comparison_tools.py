"""Comparison tools for the chat agent."""
import json
from typing import List
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage

from app.database import SessionLocal
from app.models import Resume
from app.services.llm import get_reasoning_llm


@tool
def compare_candidates(resume_ids: str, role_description: str = "") -> str:
    """Compare 2-3 candidates side by side. Pass comma-separated resume IDs and an optional role description. Use when user asks to compare specific candidates."""
    ids = [int(x.strip()) for x in resume_ids.split(",") if x.strip().isdigit()]
    if len(ids) < 2:
        return "Need at least 2 resume IDs to compare."
    if len(ids) > 3:
        ids = ids[:3]

    db = SessionLocal()
    try:
        candidates = []
        for rid in ids:
            r = db.query(Resume).filter(Resume.id == rid).first()
            if not r:
                continue
            parsed = json.loads(r.parsed_data) if r.parsed_data else {}
            exp = parsed.get("experience", [])
            candidates.append({
                "id": r.id,
                "name": r.name,
                "years": r.total_years_experience,
                "skills": json.loads(r.skills) if r.skills else [],
                "domains": json.loads(r.domain_expertise) if r.domain_expertise else [],
                "certs": json.loads(r.certifications) if r.certifications else [],
                "education": json.loads(r.education) if r.education else [],
                "current_role": exp[0].get("role", "N/A") if exp else "N/A",
                "company": exp[0].get("company", "N/A") if exp else "N/A",
            })

        if len(candidates) < 2:
            return "Could not find enough valid resumes for comparison."

        llm = get_reasoning_llm()
        cand_text = ""
        for c in candidates:
            cand_text += f"\n**{c['name']}** (ID:{c['id']})\n"
            cand_text += f"Current: {c['current_role']} at {c['company']}\n"
            cand_text += f"Experience: {c['years']} years\n"
            cand_text += f"Skills: {', '.join(c['skills'][:15])}\n"
            cand_text += f"Domain: {', '.join(c['domains'])}\n"
            cand_text += f"Education: {', '.join(c['education'])}\n"
            cand_text += f"Certifications: {', '.join(c['certs'])}\n"

        role_ctx = f"\nRole context: {role_description}" if role_description else ""

        result = llm.invoke([HumanMessage(content=f"""Compare these candidates side by side.{role_ctx}

{cand_text}

Provide:
1. Key differences between them
2. Who is stronger for each major dimension (experience, skills, domain, education)
3. A brief recommendation on who would be the better fit and why""")])

        return result.content
    finally:
        db.close()

"""Rebuild common skills/education and standardized resume fields from stored raw text."""
import argparse
import asyncio
import json
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.database import SessionLocal
from app.models import Resume, CommonSkill, CommonEducation
from app.services.llm_extractor import extract_resume_data


def _print(message: str) -> None:
    print(message, flush=True)


async def rebuild_all(resume_ids: list[int] | None = None, reset_tables: bool = True) -> None:
    db = SessionLocal()
    try:
        query = db.query(Resume).order_by(Resume.id.asc())
        if resume_ids:
            query = query.filter(Resume.id.in_(resume_ids))
        resumes = query.all()
        _print(f"Found {len(resumes)} resumes.")

        if not resumes:
            _print("Nothing to rebuild.")
            return

        if reset_tables:
            _print("Clearing common skill and education tables...")
            db.query(CommonSkill).delete()
            db.query(CommonEducation).delete()

            _print("Resetting standardized fields on stored resumes...")
            for resume in resumes:
                resume.standardized_skills = "[]"
                resume.standardized_education = "[]"
                resume.field_resolution = json.dumps({"skills": [], "education": []})
            db.commit()

        success_count = 0
        failed_count = 0

        for resume in resumes:
            _print(f"Rebuilding Resume ID {resume.id}: {resume.name}")
            parsed = await extract_resume_data(resume.raw_text or "")

            if parsed.name == "Parse Failed":
                failed_count += 1
                resume.parse_status = "failed"
                db.commit()
                _print("  parse failed; existing raw text kept, standardized values not rebuilt.")
                continue

            resume.name = parsed.name
            resume.email = parsed.email
            resume.phone = parsed.phone
            resume.skills = json.dumps(parsed.skills)
            resume.experience = json.dumps([item.model_dump() for item in parsed.experience])
            resume.education = json.dumps(parsed.education)
            resume.certifications = json.dumps(parsed.certifications)
            resume.total_years_experience = parsed.total_years_experience
            resume.domain_expertise = json.dumps(parsed.domain_expertise)
            resume.parsed_data = parsed.model_dump_json()
            resume.field_resolution = parsed.field_resolution.model_dump_json()
            resume.standardized_skills = json.dumps(parsed.standardized_skills)
            resume.standardized_education = json.dumps(parsed.standardized_education)
            resume.parse_status = "success"

            db.commit()
            success_count += 1
            _print(
                "  success"
                f" | skills: {len(parsed.standardized_skills)}"
                f" | education: {len(parsed.standardized_education)}"
            )

        _print(
            f"Rebuild complete. Success: {success_count}, Failed: {failed_count}, Total: {len(resumes)}"
        )
    except Exception as exc:
        db.rollback()
        _print(f"Rebuild failed: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-id", type=int, action="append", dest="resume_ids")
    parser.add_argument("--no-reset", action="store_true")
    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(rebuild_all(resume_ids=args.resume_ids, reset_tables=not args.no_reset))

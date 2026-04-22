"""Clean polluted common_education rows and rebuild standardized education mappings."""
import argparse
import json
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.database import SessionLocal
from app.models import Resume, CommonEducation
from app.agents.extraction_agent import (
    _clean_education_raw_value,
    _is_likely_education_value,
    resolve_with_common_table_engine,
)


def _print(message: str) -> None:
    print(message, flush=True)


def clean_common_education(apply_changes: bool = False) -> None:
    db = SessionLocal()
    try:
        all_entries = db.query(CommonEducation).all()
        kept_entries = []
        removed_entries = []

        for entry in all_entries:
            aliases = json.loads(entry.aliases) if entry.aliases else []
            cleaned_aliases = []
            for alias in aliases:
                cleaned = _clean_education_raw_value(alias)
                if cleaned and _is_likely_education_value(cleaned):
                    cleaned_aliases.append(cleaned)

            canonical_seed = " ".join([entry.name, *cleaned_aliases])
            if not _is_likely_education_value(canonical_seed):
                removed_entries.append(entry)
                continue

            entry.aliases = json.dumps(sorted(set(cleaned_aliases)))
            kept_entries.append(entry)

        _print(f"Found {len(removed_entries)} polluted common_education rows to remove.")
        for entry in removed_entries[:50]:
            _print(f"  remove: {entry.name}")

        if not apply_changes:
            _print("Dry run complete. Re-run with --apply to persist cleanup.")
            return

        for entry in removed_entries:
            db.delete(entry)
        db.flush()

        resumes = db.query(Resume).order_by(Resume.id.asc()).all()
        _print(f"Rebuilding standardized education for {len(resumes)} resumes...")
        current_entries = db.query(CommonEducation).all()

        for resume in resumes:
            raw_education = json.loads(resume.education) if resume.education else []
            mapped = resolve_with_common_table_engine("education", raw_education, current_entries, db)
            resume.standardized_education = json.dumps(sorted(set(mapped.values())))

            field_resolution = json.loads(resume.field_resolution) if resume.field_resolution else {}
            education_source = field_resolution.get("education_source", {}) if isinstance(field_resolution, dict) else {}
            for original_raw, key in mapped.items():
                education_source[key] = original_raw
            if isinstance(field_resolution, dict):
                field_resolution["education_source"] = education_source
                resume.field_resolution = json.dumps(field_resolution)

        db.commit()
        _print("Cleanup applied successfully.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist cleanup changes to the database")
    args = parser.parse_args()
    clean_common_education(apply_changes=args.apply)

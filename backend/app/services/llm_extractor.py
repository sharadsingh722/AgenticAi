"""Compatibility shim for v1 routers that import extract_resume_data/extract_tender_data.

In v2, the smart_upload router uses agents directly. These functions exist for
the legacy single-upload endpoints in resumes.py and tenders.py.
They delegate to the extraction agent for multi-pass extraction.
"""
import json
import logging

from app.agents.extraction_agent import extraction_agent
from app.schemas import ResumeParseResult, TenderParseResult

logger = logging.getLogger(__name__)


async def extract_resume_data(raw_text: str) -> ResumeParseResult:
    """Extract resume data using the multi-pass extraction agent."""
    if not raw_text.strip():
        return ResumeParseResult(name="Unknown - Empty PDF")

    try:
        result = extraction_agent.invoke({
            "raw_text": raw_text,
            "doc_type": "resume",
            "document_structure": "",
            "sections": [],
            "extracted_data": {},
            "verification_issues": [],
            "is_verified": False,
            "final_data": {},
            "pass_count": 0,
            "error": None,
        })
        data = result.get("final_data", result.get("extracted_data", {}))
        
        # Resilient sanitization
        if not isinstance(data, dict):
            logger.error("Agent returned non-dict data: %s", type(data))
            return ResumeParseResult(name="Parse Failed")

        # Ensure basic fields exist with correct types
        data.setdefault("name", "Unknown")
        
        # Ensure list fields are lists and contain only strings
        list_fields = ["skills", "education", "certifications", "domain_expertise"]
        for field in list_fields:
            if field in data:
                if not isinstance(data[field], list):
                    val = data[field]
                    data[field] = [val] if val else []
                
                # Convert any dict items to strings
                cleaned_list = []
                for item in data[field]:
                    if isinstance(item, dict):
                        # Flatten common education/skill dict formats
                        vals = [str(v) for v in item.values() if v]
                        cleaned_list.append(", ".join(vals))
                    elif item:
                        cleaned_list.append(str(item))
                data[field] = cleaned_list
            else:
                data[field] = []

        # Handle experience list specifically (it can contain dicts)
        if "experience" not in data or not isinstance(data["experience"], list):
            data["experience"] = []

        # Ensure field_resolution structure
        if "field_resolution" not in data or not isinstance(data["field_resolution"], dict):
            data["field_resolution"] = {"skills": [], "education": []}
        else:
            fr = data["field_resolution"]
            if "skills" not in fr or not isinstance(fr["skills"], list):
                fr["skills"] = []
            if "education" not in fr or not isinstance(fr["education"], list):
                fr["education"] = []

        return ResumeParseResult(**data)
    except Exception as e:
        logger.exception("Resume extraction failed: %s: %s", type(e).__name__, e)
        return ResumeParseResult(name="Parse Failed")


async def extract_tender_data(raw_text: str) -> TenderParseResult:
    """Extract tender data using the multi-pass extraction agent."""
    if not raw_text.strip():
        return TenderParseResult(project_name="Unknown - Empty PDF")

    try:
        result = extraction_agent.invoke({
            "raw_text": raw_text,
            "doc_type": "tender",
            "document_structure": "",
            "sections": [],
            "extracted_data": {},
            "verification_issues": [],
            "is_verified": False,
            "final_data": {},
            "pass_count": 0,
            "error": None,
        })
        data = result.get("final_data", result.get("extracted_data", {}))
        return TenderParseResult(**data)
    except Exception as e:
        logger.exception("Tender extraction failed: %s: %s", type(e).__name__, e)
        return TenderParseResult(project_name="Parse Failed")

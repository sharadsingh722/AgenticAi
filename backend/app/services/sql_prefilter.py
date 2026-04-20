import logging
from sqlalchemy.orm import Session
from app.models import Resume
from app.tools.db_tools import (
    filter_by_derived_profile_flag,
    filter_by_component,
    filter_by_min_project_value,
    filter_by_client_type
)

logger = logging.getLogger(__name__)

DOMAIN_TO_FLAG_MAP = {
    "railway": "has_railway_experience",
    "epc": "has_epc_experience",
    "track doubling": "has_track_doubling_experience",
    "new line": "has_new_line_experience",
    "gauge conversion": "has_gauge_conversion_experience",
    "electrification": "has_electrification_experience",
    "signalling": "has_signalling_experience",
    "telecommunication": "has_telecommunication_experience",
    "bridge": "has_bridge_or_structure_experience",
    "structure": "has_bridge_or_structure_experience",
    "survey": "has_survey_experience",
    "design": "has_design_experience",
    "testing": "has_testing_commissioning_experience",
    "commissioning": "has_testing_commissioning_experience",
    "government": "has_government_project_experience",
    "public sector": "has_public_sector_experience",
    "large scale": "has_large_scale_project_experience"
}

def build_sql_shortlist(db: Session, role: dict) -> list[int]:
    """
    Builds a SQL shortlist of resume IDs based on role requirements.
    Queries the SQLite JSON parsed_data column using helpers.
    """
    query = db.query(Resume.id).filter(Resume.parse_status == "success")

    # 1. Total Years Experience
    min_exp = role.get("min_experience", 0)
    if min_exp > 0:
        query = query.filter(Resume.total_years_experience >= min_exp)

    # 2. Required Domain Flags
    required_domains = role.get("required_domain", [])
    for domain in required_domains:
        d_lower = domain.lower()
        # Find matching flag
        flag_applied = False
        for key, flag in DOMAIN_TO_FLAG_MAP.items():
            if key in d_lower:
                query = filter_by_derived_profile_flag(query, Resume, flag)
                flag_applied = True
                break
        
        # If no specific boolean flag mapped, fallback to basic text match
        if not flag_applied:
            query = query.filter(Resume.parsed_data.ilike(f'%{domain}%'))

    # 3. Preferred Components
    preferred_components = role.get("preferred_components", [])
    for comp in preferred_components:
        query = filter_by_component(query, Resume, comp)

    # 4. Client Type Preference
    client_type = role.get("client_type_preference")
    if client_type and client_type.strip().lower() not in ["none", "any", ""]:
        query = filter_by_client_type(query, Resume, client_type)

    # 5. Min Project Value
    min_val = role.get("min_project_value_cr", 0.0)
    if min_val > 0.0:
        query = filter_by_min_project_value(query, Resume, min_val)

    # Optional: Basic Text Match for Required Skills (soft match if needed, but we keep it tight for SQL)
    # We will let vector search handle detailed skills, 
    # but we could require at least one skill match:
    # We won't overly constrain skills in SQL to avoid zero results purely from skill synonym mismatch,
    # as the vector refine will handle semantic skill matching.

    try:
        results = query.all()
        return [r[0] for r in results]
    except Exception as e:
        logger.error(f"SQL Prefilter query failed: {e}")
        return []

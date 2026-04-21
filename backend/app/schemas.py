from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# --- Resume Schemas ---

class ExperienceItem(BaseModel):
    company: str = ""
    role: str = ""
    duration: str = ""
    description: str = ""
    sector: Optional[str] = None
    subsector: Optional[str] = None
    client_type: Optional[str] = None
    components: List[str] = Field(default_factory=list)
    project_value_cr: float = 0.0
    length_km: float = 0.0
    location: Optional[str] = None

class DerivedProfile(BaseModel):
    has_railway_experience: bool = False
    has_epc_experience: bool = False
    has_track_doubling_experience: bool = False
    has_new_line_experience: bool = False
    has_gauge_conversion_experience: bool = False
    has_electrification_experience: bool = False
    has_signalling_experience: bool = False
    has_telecommunication_experience: bool = False
    has_bridge_or_structure_experience: bool = False
    has_survey_experience: bool = False
    has_design_experience: bool = False
    has_testing_commissioning_experience: bool = False
    has_government_project_experience: bool = False
    has_public_sector_experience: bool = False
    has_large_scale_project_experience: bool = False
    max_project_value_cr: float = 0.0
    max_project_length_km: float = 0.0
    railway_project_count: int = 0
    epc_project_count: int = 0
    relevant_project_count: int = 0


class FieldResolutionItem(BaseModel):
    raw_value: str = ""
    normalized_value: str = ""
    common_table_match: Optional[str] = None
    resolution_method: str = "new"
    final_common_value: str = ""


class FieldResolution(BaseModel):
    skills_source: dict[str, str] = Field(default_factory=dict)
    education_source: dict[str, str] = Field(default_factory=dict)
    domain_source: dict[str, str] = Field(default_factory=dict)


class ResumeParseResult(BaseModel):
    name: str = "Unknown"
    email: Optional[str] = None
    phone: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    experience: List[ExperienceItem] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    total_years_experience: float = 0.0
    domain_expertise: List[str] = Field(default_factory=list)
    field_resolution: FieldResolution = Field(default_factory=FieldResolution)
    standardized_skills: List[str] = Field(default_factory=list)
    standardized_education: List[str] = Field(default_factory=list)
    derived_profile: DerivedProfile = Field(default_factory=DerivedProfile)


class ResumeResponse(BaseModel):
    id: int
    name: str
    email: Optional[str]
    phone: Optional[str]
    skills: List[str]
    total_years_experience: float
    domain_expertise: List[str]
    file_name: str
    photo_url: Optional[str] = None
    pdf_filename: Optional[str] = None
    parse_status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ResumeDetailResponse(ResumeResponse):
    experience: List[ExperienceItem]
    education: List[str]
    certifications: List[str]
    raw_text: str
    field_resolution: Optional[FieldResolution] = None
    standardized_skills: List[str] = []
    standardized_education: List[str] = []
    derived_profile: Optional[DerivedProfile] = None


# --- Tender Schemas ---

class RequiredRole(BaseModel):
    role_title: str = ""
    min_experience: float = 0.0
    required_skills: List[str] = Field(default_factory=list)
    required_certifications: List[str] = Field(default_factory=list)
    required_domain: List[str] = Field(default_factory=list)
    preferred_components: List[str] = Field(default_factory=list)
    min_project_value_cr: float = 0.0
    client_type_preference: Optional[str] = None


class TenderParseResult(BaseModel):
    project_name: str = "Unknown Project"
    client: Optional[str] = None
    document_reference: Optional[str] = None
    document_date: Optional[str] = None
    required_roles: List[RequiredRole] = Field(default_factory=list)
    eligibility_criteria: List[str] = Field(default_factory=list)
    project_duration: Optional[str] = None
    key_technologies: List[str] = Field(default_factory=list)


class TenderResponse(BaseModel):
    id: int
    project_name: str
    client: Optional[str]
    document_reference: Optional[str] = None
    document_date: Optional[str] = None
    roles_count: int
    key_technologies: List[str]
    file_name: str
    pdf_filename: Optional[str] = None
    parse_status: str
    created_at: datetime

    class Config:
        from_attributes = True


class TenderDetailResponse(BaseModel):
    id: int
    project_name: str
    client: Optional[str]
    document_reference: Optional[str] = None
    document_date: Optional[str] = None
    required_roles: List[RequiredRole]
    eligibility_criteria: List[str]
    project_duration: Optional[str]
    key_technologies: List[str]
    file_name: str
    pdf_filename: Optional[str] = None
    parse_status: str
    raw_text: str
    created_at: datetime

    class Config:
        from_attributes = True


# --- Match Schemas ---

class ScoreBreakdown(BaseModel):
    experience: float = 0.0
    skills: float = 0.0
    domain: float = 0.0
    certifications: float = 0.0
    education: float = 0.0


class MatchResultItem(BaseModel):
    resume_id: int
    candidate_name: str
    role_title: str
    final_score: float
    semantic_score: float
    structured_score: float
    score_breakdown: ScoreBreakdown
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    experience_years: float = 0.0
    designation: Optional[str] = None
    photo_url: Optional[str] = None
    # V2: LLM-as-judge fields
    llm_score: Optional[float] = None
    llm_explanation: Optional[str] = None
    strengths: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)


class ScoringCriterion(BaseModel):
    criterion: str
    weight: float
    description: str


class RoleRequirements(BaseModel):
    min_experience: float = 0.0
    required_skills: List[str] = Field(default_factory=list)
    required_certifications: List[str] = Field(default_factory=list)
    required_domain: List[str] = Field(default_factory=list)
    preferred_components: List[str] = Field(default_factory=list)
    min_project_value_cr: float = 0.0
    client_type_preference: Optional[str] = None


class MatchResponse(BaseModel):
    tender_id: int
    project_name: str
    role_title: str
    role_requirements: Optional[RoleRequirements] = None
    scoring_criteria: List[ScoringCriterion] = Field(default_factory=list)
    results: List[MatchResultItem]


class MatchSummary(BaseModel):
    tender_id: int
    project_name: str
    roles: List[str]
    total_matches: int
    created_at: datetime


# --- Chat Schemas ---

class ChatSessionResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatMessageResponse(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    tool_calls: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

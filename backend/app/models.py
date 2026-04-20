from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from app.database import Base


class CommonSkill(Base):
    __tablename__ = "common_skills"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, unique=True, index=True)
    aliases = Column(Text, default="[]")


class CommonEducation(Base):
    __tablename__ = "common_education"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, unique=True, index=True)
    aliases = Column(Text, default="[]")
    level = Column(String, nullable=True)  # graduate | postgraduate | phd | diploma | highschool | other


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    skills = Column(Text, default="[]")
    experience = Column(Text, default="[]")
    education = Column(Text, default="[]")
    certifications = Column(Text, default="[]")
    total_years_experience = Column(Float, default=0.0)
    domain_expertise = Column(Text, default="[]")
    raw_text = Column(Text, nullable=False)
    markdown_text = Column(Text, nullable=True) # High-fidelity MD
    file_name = Column(String, nullable=False)
    photo_filename = Column(String, nullable=True)
    pdf_filename = Column(String, nullable=True) # Backup filename for download
    parsed_data = Column(Text, default="{}")
    field_resolution = Column(Text, default="{}")
    standardized_skills = Column(Text, default="[]") # JSON list of common names
    standardized_education = Column(Text, default="[]") # JSON list of common names
    parse_status = Column(String, default="success")
    rag_status = Column(String, default="pending") # pending | indexing | completed | failed
    created_at = Column(DateTime, default=datetime.utcnow)

    match_results = relationship("MatchResult", back_populates="resume", cascade="all, delete-orphan")
    chunks = relationship("ResumeChunk", back_populates="resume", cascade="all, delete-orphan")


class ResumeChunk(Base):
    __tablename__ = "resume_chunks"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    
    resume = relationship("Resume", back_populates="chunks")


class Tender(Base):
    __tablename__ = "tenders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_name = Column(String, nullable=False)
    client = Column(String, nullable=True)
    document_reference = Column(String, nullable=True)
    document_date = Column(String, nullable=True)
    required_roles = Column(Text, default="[]")
    eligibility_criteria = Column(Text, default="[]")
    project_duration = Column(String, nullable=True)
    key_technologies = Column(Text, default="[]")
    raw_text = Column(Text, nullable=False)
    markdown_text = Column(Text, nullable=True) # High-fidelity MD
    file_name = Column(String, nullable=False)
    pdf_filename = Column(String, nullable=True) # Backup filename for download
    parsed_data = Column(Text, default="{}")
    parse_status = Column(String, default="success")
    rag_status = Column(String, default="pending") # pending | indexing | completed | failed
    created_at = Column(DateTime, default=datetime.utcnow)

    match_results = relationship("MatchResult", back_populates="tender", cascade="all, delete-orphan")
    chunks = relationship("TenderChunk", back_populates="tender", cascade="all, delete-orphan")


class TenderChunk(Base):
    __tablename__ = "tender_chunks"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tender_id = Column(Integer, ForeignKey("tenders.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    
    tender = relationship("Tender", back_populates="chunks")


class MatchResult(Base):
    __tablename__ = "match_results"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tender_id = Column(Integer, ForeignKey("tenders.id"), nullable=False)
    role_title = Column(String, nullable=False)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=False)
    semantic_score = Column(Float, default=0.0)
    structured_score = Column(Float, default=0.0)
    final_score = Column(Float, default=0.0)
    score_breakdown = Column(Text, default="{}")
    # V2: LLM-as-judge fields
    llm_score = Column(Float, nullable=True)
    llm_explanation = Column(Text, nullable=True)
    strengths = Column(Text, nullable=True)  # JSON list
    concerns = Column(Text, nullable=True)  # JSON list
    scoring_criteria = Column(Text, nullable=True)  # JSON list
    created_at = Column(DateTime, default=datetime.utcnow)

    tender = relationship("Tender", back_populates="match_results")
    resume = relationship("Resume", back_populates="match_results")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)  # user | assistant | tool
    content = Column(Text, nullable=False)
    tool_calls = Column(Text, nullable=True)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow)

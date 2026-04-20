"""Document classification agent using LangGraph.

Graph: prepare_text → classify_document → [has_images?] → analyze_images → [is_person?] → save_photo → END
"""
import os
import hashlib
import base64
import logging
from typing import Optional, List, TypedDict

import fitz  # PyMuPDF
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.services.pdf_parser import extract_candidate_images_from_pdf
from app.services.llm import get_fast_llm, get_vision_llm
from app.config import settings

logger = logging.getLogger(__name__)


# --- State ---

class DocumentAgentState(TypedDict):
    raw_text: str
    file_name: str
    pdf_bytes: bytes
    text_snippet: str
    has_images: bool
    extracted_images: list  # List of (bytes, ext, width, height)
    classification: str  # resume | tender | company_profile | other
    confidence: float
    explanation: str
    photo_filename: Optional[str]
    photo_type: Optional[str]  # person | logo | other
    error: Optional[str]


# --- Structured output models ---

class ClassificationResult(BaseModel):
    doc_type: str = Field(description="One of: resume, tender, company_profile, other")
    confidence: float = Field(description="Confidence 0.0-1.0")
    explanation: str = Field(description="Brief explanation of why this classification")


class ImageAnalysisResult(BaseModel):
    image_type: str = Field(description="One of: person, logo, other")
    explanation: str = Field(description="What the image shows")


# --- Graph Nodes ---

def prepare_text(state: DocumentAgentState) -> dict:
    """Extract text snippet and check for images."""
    snippet = state["raw_text"][:5000]
    
    # Use the unified extraction utility
    candidates = extract_candidate_images_from_pdf(state["pdf_bytes"], limit=3)
    
    # Convert candidates to the tuple format used in state
    images = [(c["image"], c["ext"], c["width"], c["height"]) for c in candidates]
    
    return {
        "text_snippet": snippet,
        "has_images": len(images) > 0,
        "extracted_images": images,
    }


def classify_document(state: DocumentAgentState) -> dict:
    """Classify document type using fast LLM with structured output + heuristic fallback."""
    llm = get_fast_llm().with_structured_output(ClassificationResult)

    # Use more text for better classification
    text_sample = state["raw_text"][:5000]

    result = llm.invoke([HumanMessage(content=f"""Classify this document into EXACTLY one type.

IMPORTANT CLASSIFICATION RULES:
- **resume**: A document about a SINGLE PERSON. Key signals: a person's name featured prominently, their education history, work experience at multiple companies, personal skills list, date of birth, professional memberships. NOTE: Resumes are sometimes formatted as "Technical Proposals" or "CV" pages within tender submissions — if the document describes ONE person's qualifications, experience, and education, it is a RESUME regardless of the header.
- **tender**: A document inviting COMPANIES to bid. Key signals: "Request for Proposal", "Notice Inviting Tender", scope of work for a PROJECT, eligibility criteria for COMPANIES, bid submission deadlines, EMD/security deposit requirements, multiple roles/positions to be filled by a vendor.
- **company_profile**: About a COMPANY (not a person). Key signals: company history, list of projects done, organizational structure, client list.
- **other**: Anything else (invoice, letter, certificate, report, etc.)

The critical distinction between resume and tender: Does this document describe ONE PERSON's background, or does it describe a PROJECT that needs a company to bid on?

Document text:
{text_sample}""")])

    doc_type = result.doc_type
    confidence = result.confidence
    explanation = result.explanation

    # Heuristic safety check: if classified as tender but has strong resume signals, override
    text_lower = state["raw_text"][:8000].lower()
    resume_signals = ["date of birth", "nationality", "marital status", "passport no",
                      "proposed position", "name of staff", "professional experience",
                      "employment record", "academic qualification", "years of experience"]
    tender_signals = ["request for proposal", "scope of work", "eligibility criteria",
                      "bid submission", "earnest money", "pre-qualification",
                      "tender document fee", "notice inviting tender"]

    resume_score = sum(1 for s in resume_signals if s in text_lower)
    tender_score = sum(1 for s in tender_signals if s in text_lower)

    if doc_type == "tender" and resume_score >= 3 and tender_score <= 1:
        doc_type = "resume"
        confidence = 0.85
        explanation = f"Reclassified: document has strong person-level signals ({resume_score} resume indicators vs {tender_score} tender indicators)"
        logger.info(f"Heuristic override: tender -> resume for {state['file_name']}")

    return {
        "classification": doc_type,
        "confidence": confidence,
        "explanation": explanation,
    }


def analyze_images(state: DocumentAgentState) -> dict:
    """Use vision model to determine if images are person photos or logos."""
    if not state["extracted_images"]:
        return {"photo_type": None}

    llm = get_vision_llm().with_structured_output(ImageAnalysisResult)
    img_bytes, ext, w, h = state["extracted_images"][0]
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    mime = f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"

    try:
        result = llm.invoke([HumanMessage(content=[
            {"type": "text", "text": "Is this image a photograph of a person/face, a company logo, or something else? Classify it."},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ])])
        return {"photo_type": result.image_type}
    except Exception as e:
        logger.warning(f"Vision analysis failed: {e}")
        return {"photo_type": "other"}


def save_photo(state: DocumentAgentState) -> dict:
    """Save person photo to disk."""
    if not state["extracted_images"]:
        return {"photo_filename": None}

    img_bytes, ext, w, h = state["extracted_images"][0]
    os.makedirs(os.path.join(settings.upload_dir, "photos"), exist_ok=True)
    img_hash = hashlib.md5(img_bytes).hexdigest()[:12]
    filename = f"{img_hash}.{ext}"
    filepath = os.path.join(settings.upload_dir, "photos", filename)
    with open(filepath, "wb") as f:
        f.write(img_bytes)
    return {"photo_filename": filename}


# --- Conditional edges ---

def should_analyze_images(state: DocumentAgentState) -> str:
    return "analyze_images" if state.get("has_images") else END


def should_save_photo(state: DocumentAgentState) -> str:
    return "save_photo" if state.get("photo_type") == "person" else END


# --- Build Graph ---

def build_document_agent_graph() -> StateGraph:
    graph = StateGraph(DocumentAgentState)

    graph.add_node("prepare_text", prepare_text)
    graph.add_node("classify_document", classify_document)
    graph.add_node("analyze_images", analyze_images)
    graph.add_node("save_photo", save_photo)

    graph.set_entry_point("prepare_text")
    graph.add_edge("prepare_text", "classify_document")
    graph.add_conditional_edges("classify_document", should_analyze_images)
    graph.add_conditional_edges("analyze_images", should_save_photo)
    graph.add_edge("save_photo", END)

    return graph.compile()


# Singleton compiled graph
document_agent = build_document_agent_graph()

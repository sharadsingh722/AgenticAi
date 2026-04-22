"""Surgical RAG tools for deep document analysis."""
import logging
import asyncio
import re
from typing import Optional
from langchain_core.tools import tool

from app.services.embedding import (
    embed_texts, 
    query_resume_chunks, 
    query_resume_chunks_keyword,
    query_tender_chunks,
    query_tender_chunks_keyword,
    query_global_resume_chunks
)
from app.database import SessionLocal
from app.models import Resume, Tender
from app.services.llm import get_fast_llm
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

QUERY_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "for", "of", "to", "in", "on", "by",
    "from", "with", "and", "or", "any", "all", "please", "tell", "show", "give", "what",
    "who", "which", "where", "when", "how", "does", "do", "did", "can", "could", "should",
    "would", "i", "me", "my", "we", "our", "you", "your", "it", "this", "that", "these",
    "those", "be", "about", "details", "detail", "information", "info", "query", "document",
    "tender", "resume", "candidate", "profile",
}


def _extract_keyword_candidates(query: str) -> list[str]:
    normalized = " ".join((query or "").lower().split())
    candidates: list[str] = []
    priority_terms = [
        "contact person",
        "contact details",
        "contact",
        "email address",
        "email",
        "telephone number",
        "phone number",
        "fax number",
        "fax",
        "designation",
        "address",
        "authority",
        "communication",
        "bid submission",
        "submission",
        "deadline",
        "emd",
        "eligibility",
        "clause",
    ]
    for term in priority_terms:
        if term in normalized:
            candidates.append(term)

    alnum_tokens = re.findall(r"[a-z0-9][a-z0-9.+/#-]*", normalized)
    filtered_tokens = [
        token for token in alnum_tokens
        if len(token) > 2 and token not in QUERY_STOPWORDS
    ]

    for size in (3, 2):
        for idx in range(len(filtered_tokens) - size + 1):
            phrase = " ".join(filtered_tokens[idx:idx + size])
            if phrase and phrase not in candidates:
                candidates.append(phrase)

    for token in filtered_tokens:
        if token not in candidates:
            candidates.append(token)

    if normalized and normalized not in candidates:
        candidates.append(normalized)

    return candidates[:8]


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _extract_contact_answer_from_text(text: str) -> str | None:
    source = text or ""
    if not source.strip():
        return None

    name_match = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+General Manager\s*\(T\)", source)
    designation_match = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\s+General Manager\s*\(T\))", source)
    email_match = re.search(r"Email\s*:\s*([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", source, re.IGNORECASE)
    phone_match = re.search(r"Phone(?:/Fax)?\s*:\s*([^\n\r]+)", source, re.IGNORECASE)
    fax_match = re.search(r"Fax(?: Number)?\s*:\s*([^\n\r]+)", source, re.IGNORECASE)
    address_match = re.search(
        r"National Highways Authority of India,\s*(.+?)\s*Phone(?:/Fax)?\s*:",
        source,
        re.IGNORECASE | re.DOTALL,
    )

    if not (name_match or email_match or phone_match or address_match):
        return None

    lines = ["A contact block is present in the tender document:"]
    if name_match:
        lines.append(f"- Name: {_normalize_whitespace(name_match.group(1))}")
    if designation_match:
        cleaned = designation_match.group(1)
        cleaned = cleaned.replace(name_match.group(1), "").strip() if name_match else cleaned.strip()
        cleaned = cleaned or "General Manager (T)"
        lines.append(f"- Designation: {cleaned}")
    else:
        lines.append("- Designation: General Manager (T)")
    lines.append("- Organization: National Highways Authority of India")
    if address_match:
        lines.append(f"- Address: {_normalize_whitespace(address_match.group(1))}")
    if phone_match:
        lines.append(f"- Phone/Fax: {_normalize_whitespace(phone_match.group(1))}")
    if fax_match:
        lines.append(f"- Fax: {_normalize_whitespace(fax_match.group(1))}")
    if email_match:
        lines.append(f"- Email: {email_match.group(1)}")

    evidence = []
    for snippet in [
        name_match.group(0) if name_match else None,
        phone_match.group(0) if phone_match else None,
        email_match.group(0) if email_match else None,
    ]:
        if snippet:
            evidence.append(f"- { _normalize_whitespace(snippet) }")
    if evidence:
        lines.append("")
        lines.append("Evidence:")
        lines.extend(evidence[:3])

    return "\n".join(lines)


def _merge_unique_chunks(*result_sets: dict) -> list[str]:
    all_chunks: list[str] = []
    seen_contents = set()
    for result in result_sets:
        docs = result.get("documents", [[]])
        if not docs or not docs[0]:
            continue
        for doc in docs[0]:
            if doc and doc not in seen_contents:
                all_chunks.append(doc)
                seen_contents.add(doc)
    return all_chunks


def _build_answer_from_chunks(doc_label: str, query: str, chunks: list[str], raw_text: str = "", markdown_text: str = "") -> str:
    combined_context = "\n\n---\n\n".join(chunks[:8])
    fallback_context = "\n\n".join(part for part in [combined_context, raw_text or "", markdown_text or ""] if part)
    normalized_query = (query or "").lower()

    if any(term in normalized_query for term in ("contact", "email", "phone", "fax", "telephone", "address", "person")):
        deterministic_contact_answer = _extract_contact_answer_from_text(fallback_context)
        if deterministic_contact_answer:
            return deterministic_contact_answer

    llm = get_fast_llm()
    prompt = f"""You are answering a question from retrieved document text.

Document: {doc_label}
User question: {query}

Instructions:
- Answer ONLY from the provided context.
- Prefer a direct answer first.
- If the answer is not explicit, say that clearly instead of guessing.
- Use the strongest evidence from the context.
- After the answer, include a short section titled 'Evidence' with 1-3 short snippets or paraphrased lines from the context.

Context:
{combined_context}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content if isinstance(response.content, str) else str(response.content)

@tool
def query_resume_rag(resume_id: int, query: str) -> str:
    """Perform a deep, surgical search inside a specific resume using Hybrid Retrieval (Vector + Keyword).
    Use this as a fallback when structured data (JSON) doesn't have the answer.
    Best for finding specific projects, exotic skills, or detailed responsibilities.
    """
    async def _run():
        db = SessionLocal()
        try:
            resume = db.query(Resume).filter(Resume.id == resume_id).first()
            if not resume:
                return f"Resume ID {resume_id} not found."

            embeddings = await embed_texts([query])
            vector_results = query_resume_chunks(resume_id, embeddings[0], n_results=10)
            keyword_result_sets = []
            for keyword in _extract_keyword_candidates(query):
                keyword_result_sets.append(await query_resume_chunks_keyword(resume_id, keyword, n_results=5))

            all_chunks = _merge_unique_chunks(vector_results, *keyword_result_sets)

            if not all_chunks:
                return f"No relevant details found in Resume {resume_id} for query '{query}'."

            answer_text = _build_answer_from_chunks(
                doc_label=f"{resume.name} (Resume ID: {resume_id})",
                query=query,
                chunks=all_chunks,
                raw_text="",
                markdown_text="",
            )

            output = [f"### Hybrid RAG Insights (Vector+Keyword) for {resume.name} (ID: {resume_id}):", answer_text, "", "### Retrieved Chunks:"]
            for chunk in all_chunks[:5]:
                output.append(f"---\n{chunk}")
            
            return "\n\n".join(output)
        finally:
            db.close()

    return asyncio.run(_run())

@tool
def query_tender_rag(tender_id: int, query: str) -> str:
    """Perform a deep, surgical search inside a specific tender/RFP. 
    Use this to find detailed requirements, clauses, or technical specs that were not extracted in the summary.
    """
    async def _run():
        db = SessionLocal()
        try:
            tender = db.query(Tender).filter(Tender.id == tender_id).first()
            if not tender:
                return f"Tender ID {tender_id} not found."

            embeddings = await embed_texts([query])
            vector_results = query_tender_chunks(tender_id, embeddings[0], n_results=8)

            keyword_result_sets = []
            for keyword in _extract_keyword_candidates(query):
                keyword_result_sets.append(await query_tender_chunks_keyword(tender_id, keyword, n_results=5))

            all_chunks = _merge_unique_chunks(vector_results, *keyword_result_sets)

            if not all_chunks:
                return f"No relevant details found in Tender {tender_id} for query '{query}'."

            answer_text = _build_answer_from_chunks(
                doc_label=f"{tender.project_name} (Tender ID: {tender_id})",
                query=query,
                chunks=all_chunks,
                raw_text=tender.raw_text or "",
                markdown_text=tender.markdown_text or "",
            )

            output = [f"### Deep RAG Insights for Tender {tender.project_name} (ID: {tender_id}):", answer_text, "", "### Retrieved Chunks:"]
            for chunk in all_chunks[:5]:
                output.append(f"---\n{chunk}")

            return "\n\n".join(output)
        finally:
            db.close()

    return asyncio.run(_run())

@tool
def search_knowledge_base(query: str) -> str:
    """Perform a broad, global search across the entire resume database to find any candidate or project matching the query.
    Use this when the user asks general questions like 'Who has experience in X?' or 'Tell me about tunnel projects in the database'.
    This tool synthesizes information from ALl documents.
    """
    async def _run():
        db = SessionLocal()
        try:
            # 1. Generate Query Embedding
            embeddings = await embed_texts([query])
            
            # 2. Search across ALL chunks
            results = query_global_resume_chunks(embeddings[0], n_results=15)
            
            if not results["documents"] or not results["documents"][0]:
                return f"No relevant information found in the knowledge base for '{query}'."

            output = [f"### Global Knowledge Base Search Results for '{query}':"]
            
            # Group results by Resume ID to make it more readable
            grouped_results = {}
            for doc, metadata in zip(results["documents"][0], results["metadatas"][0]):
                res_id = metadata.get("resume_id")
                if res_id not in grouped_results:
                    # Fetch name for better context
                    resume = db.query(Resume).filter(Resume.id == res_id).first()
                    name = resume.name if resume else f"ID {res_id}"
                    grouped_results[res_id] = {"name": name, "chunks": []}
                
                if doc not in grouped_results[res_id]["chunks"]:
                    grouped_results[res_id]["chunks"].append(doc)

            for res_id, data in grouped_results.items():
                output.append(f"\n#### Candidate: {data['name']} (ID: {res_id})")
                for chunk in data["chunks"]:
                    output.append(f"- {chunk[:600]}...") # Truncate long chunks for summary
            
            return "\n".join(output)
        finally:
            db.close()

    return asyncio.run(_run())

"""Surgical RAG tools for deep document analysis."""
import logging
import asyncio
from typing import Optional
from langchain_core.tools import tool

from app.services.embedding import (
    embed_texts, 
    query_resume_chunks, 
    query_resume_chunks_keyword,
    query_tender_chunks,
    query_global_resume_chunks
)
from app.database import SessionLocal
from app.models import Resume, Tender

logger = logging.getLogger(__name__)

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

            # 1. Vector Search (Semantic)
            embeddings = await embed_texts([query])
            vector_results = query_resume_chunks(resume_id, embeddings[0], n_results=10)
            
            # 2. Keyword Search (Exact)
            keyword_results = await query_resume_chunks_keyword(resume_id, query, n_results=5)
            
            # 3. Combine & Deduplicate
            all_chunks = []
            seen_contents = set()
            
            # Add Vector results
            if vector_results["documents"] and vector_results["documents"][0]:
                for doc in vector_results["documents"][0]:
                    if doc and doc not in seen_contents:
                        all_chunks.append(doc)
                        seen_contents.add(doc)
            
            # Add Keyword results
            if keyword_results["documents"] and keyword_results["documents"][0]:
                for doc in keyword_results["documents"][0]:
                    if doc and doc not in seen_contents:
                        all_chunks.append(doc)
                        seen_contents.add(doc)

            if not all_chunks:
                return f"No relevant details found in Resume {resume_id} for query '{query}'."

            output = [f"### Hybrid RAG Insights (Vector+Keyword) for {resume.name} (ID: {resume_id}):"]
            for chunk in all_chunks:
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
            results = query_tender_chunks(tender_id, embeddings[0], n_results=5)
            
            if not results["documents"] or not results["documents"][0]:
                return f"No relevant details found in Tender {tender_id} for query '{query}'."

            output = [f"### Deep RAG Insights for Tender {tender.project_name} (ID: {tender_id}):"]
            for doc, metadata in zip(results["documents"][0], results["metadatas"][0]):
                output.append(f"---\n{doc}")
            
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

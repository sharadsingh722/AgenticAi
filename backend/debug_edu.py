
import sys
import os

# Mock the functions from db_tools
import re

def _normalize_lookup_text(value: str) -> str:
    if not value:
        return ""
    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"\b(19|20)\d{2}\b", " ", normalized)
    normalized = re.sub(r"[_/\\-]+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9\s]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized

def _education_semantic_terms(value: str) -> list[str]:
    normalized = _normalize_lookup_text(value)
    if not normalized:
        return []
    terms = []
    tokens = set(normalized.split())
    if {"graduate", "graduation"} & tokens or "graduate" in normalized or "graduation" in normalized:
        terms.extend(["graduate", "bachelor"])
    if {"post", "postgraduate", "postgraduation", "master", "masters"} & tokens or "postgraduate" in normalized or "master" in normalized:
        terms.extend(["postgraduate", "master"])
    return terms

test_edu = "Post Graduate M En .T g e in c e h e r M in E g i o n r S e t q ru u c iv t a u l r e a n l t Structural Engineering VITAM College JNTU Campus 2016 CC292440 -- Download File View"
norm = _normalize_lookup_text(test_edu)
print(f"Normalized: {norm}")
terms = _education_semantic_terms(test_edu)
print(f"Terms: {terms}")

query_edu = "Masters"
query_norm = _normalize_lookup_text(query_edu)
query_terms = _education_semantic_terms(query_edu)
print(f"Query Terms: {query_terms}")

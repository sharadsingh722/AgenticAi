"""LLM service layer with model routing.

Provides fast (4o-mini), reasoning (4o), and vision (4o) model access
via LangChain ChatOpenAI wrappers.
"""
import logging
from functools import lru_cache
from langchain_openai import ChatOpenAI
from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache()
def get_fast_llm() -> ChatOpenAI:
    """GPT-4o-mini for classification, verification, simple tasks."""
    return ChatOpenAI(
        model=settings.fast_model,
        temperature=0.1,
        api_key=settings.openai_api_key,
    )


@lru_cache()
def get_reasoning_llm() -> ChatOpenAI:
    """GPT-4o for deep extraction, matching judgments, chat reasoning."""
    return ChatOpenAI(
        model=settings.reasoning_model,
        temperature=0.2,
        api_key=settings.openai_api_key,
    )


@lru_cache()
def get_vision_llm() -> ChatOpenAI:
    """GPT-4o with vision for image analysis (photo vs logo)."""
    return ChatOpenAI(
        model=settings.vision_model,
        temperature=0.1,
        api_key=settings.openai_api_key,
    )

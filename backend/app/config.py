import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    database_url: str = "sqlite:///./data/resume_tender.db"
    chroma_persist_dir: str = "./data/chroma_store"
    upload_dir: str = "./data/uploads"

    # Model routing
    reasoning_model: str = "gpt-4o"
    fast_model: str = "gpt-4o-mini"
    vision_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Agent config
    max_extraction_passes: int = 3
    chat_max_history: int = 20
    top_k_candidates: int = 20
    min_match_score: float = 25.0

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()


BASE_DIR = Path(__file__).resolve().parents[1]


def _resolve_path(path_value: str) -> str:
    path = Path(path_value)
    if path.is_absolute():
        return str(path)
    return str((BASE_DIR / path).resolve())


def _resolve_database_url(database_url: str) -> str:
    sqlite_prefix = "sqlite:///"
    if database_url.startswith(sqlite_prefix):
        raw_path = database_url[len(sqlite_prefix):]
        if raw_path and not Path(raw_path).is_absolute():
            return f"{sqlite_prefix}{_resolve_path(raw_path)}"
    return database_url


settings.database_url = _resolve_database_url(settings.database_url)
settings.chroma_persist_dir = _resolve_path(settings.chroma_persist_dir)
settings.upload_dir = _resolve_path(settings.upload_dir)

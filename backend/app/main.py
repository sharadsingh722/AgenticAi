import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine, Base
from app.routers import resumes, tenders, matching, smart_upload, chat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

app = FastAPI(
    title="Resume-Tender Matcher V2 (Agentic)",
    description="AI-powered system with LangGraph agents for document analysis, matching, and natural language search",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(resumes.router, prefix="/api")
app.include_router(tenders.router, prefix="/api")
app.include_router(matching.router, prefix="/api")
app.include_router(smart_upload.router, prefix="/api")
app.include_router(chat.router, prefix="/api")


def _sqlite_column_exists(connection, table_name: str, column_name: str) -> bool:
    rows = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def _ensure_sqlite_compatibility() -> None:
    """Add a few missing columns when opening older SQLite databases."""
    with engine.begin() as connection:
        dialect = connection.dialect.name
        if dialect != "sqlite":
            return

        if not _sqlite_column_exists(connection, "resumes", "pdf_filename"):
            connection.execute(text("ALTER TABLE resumes ADD COLUMN pdf_filename VARCHAR"))

        if not _sqlite_column_exists(connection, "tenders", "pdf_filename"):
            connection.execute(text("ALTER TABLE tenders ADD COLUMN pdf_filename VARCHAR"))


@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_compatibility()
    os.makedirs(os.path.join(settings.upload_dir, "resumes"), exist_ok=True)
    os.makedirs(os.path.join(settings.upload_dir, "tenders"), exist_ok=True)
    os.makedirs(os.path.join(settings.upload_dir, "photos"), exist_ok=True)
    os.makedirs(settings.chroma_persist_dir, exist_ok=True)
    logging.info("Resume-Tender Matcher V2 (Agentic) started")


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "2.0.0"}

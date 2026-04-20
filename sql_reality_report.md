# SQL Architecture Reality Report

> [!IMPORTANT]
> This is a deep-dive inspection report of the current Resume-Tender Matching system database layer. This report is designed to be shared with another AI assistant to build correct natural-language-to-SQL logic based on the *actual* implementation.

## A. Database Overview

- **Current Database Used:** SQLite 
- **Connection String:** `sqlite:///./data/resume_tender.db` (defined in `backend/app/config.py`)
- **ORM / Engine:** SQLAlchemy (`create_engine`, `sessionmaker`, `declarative_base`)
- **Session Management:** Standard FastAPI dependency injection (`Depends(get_db)`) using a request-scoped `SessionLocal`.
- **Migration System:** None detected (uses `Base.metadata.create_all(bind=engine)` implicitly, lacking Alembic).
- **Core Pattern:** The architecture relies heavily on holding data in **JSON stringified text blobs** (e.g., `parsed_data`, `skills`, `experience`) rather than normalized relational tables. Active querying is almost entirely done via ORM, not raw SQL.

---

## B. SQL-Related Files List

Here is every file interacting with the database:

1. `backend/app/database.py` (Engine and session config)
2. `backend/app/models.py` (SQLAlchemy schemas)
3. `backend/app/routers/resumes.py` (CRUD for resumes)
4. `backend/app/routers/tenders.py` (CRUD for tenders)
5. `backend/app/routers/smart_upload.py` (Insert operations for parsing)
6. `backend/app/routers/matching.py` (Reads for matching, Writes for results)
7. `backend/app/services/structured_scorer.py` (Clears/Writes match results, reads Tenders/Resumes)
8. `backend/app/tools/db_tools.py` (Tool functions for LangChain/OpenAI chat)
9. `backend/app/tools/search_tools.py` (Fetches DB records by ID after vector search)
10. `backend/backfill_resumes.py`, `reprocess_resumes.py`, `relink_resumes.py` (Maintenance scripts executing mass DB updates)

---

## C. Exact Code Blocks by File

### 1. `backend/app/routers/matching.py` (Match Orchestration)
**Action:** Reads Tender, Reads Resumes, Deletes old MatchResults, Inserts new MatchResults.
**Type:** SQLAlchemy ORM
```python
# Fetch Tender
tender = db.query(Tender).filter(Tender.id == tender_id).first()

# Fetch All Resumes for Dictionary Lookup
all_resumes = db.query(Resume).filter(Resume.parse_status == "success").all()

# Delete Previous Match Results for this Tender
db.query(MatchResult).filter(MatchResult.tender_id == tender_id).delete()
db.commit()

# Insert New Match Results
db_match = MatchResult(
    tender_id=tender_id,
    role_title=role.role_title,
    resume_id=rid,
    final_score=hybrid_final,
    structured_score=round(struct_score, 2),
    llm_score=llm_score,
    llm_explanation=explanation,
    strengths=json.dumps(strengths),
    concerns=json.dumps(concerns),
    scoring_criteria=json.dumps([c.model_dump() for c in scoring_criteria]),
    score_breakdown=json.dumps(breakdown.model_dump()),
)
db.add(db_match)
```

### 2. `backend/app/agents/matching_agent.py` (Candidate Pre-Filter)
**Action:** Notice that it does **NOT** use SQL to filter candidate resumes. It uses Vector Search.
**Type:** Vector DB / ChromaDB (No SQL)
```python
# From pre_filter()
results = query_similar_resumes(embedding, n_results=settings.top_k_candidates)

candidate_ids = []
if results["ids"] and results["ids"][0]:
    candidate_ids = [int(rid) for rid in results["ids"][0]]

return {"candidate_resumes": [{"resume_id": rid} for rid in candidate_ids]}
```

### 3. `backend/app/routers/smart_upload.py` (Document Ingestion)
**Action:** Insert new documents into SQLite database.
**Type:** SQLAlchemy ORM 
```python
# Insert Resume
db_resume = Resume(
    name=file.filename,
    file_name=file.filename,
    raw_text=raw_text,
    pdf_filename=pdf_backup_filename,
    parse_status="processing"
)
db.add(db_resume)
db.commit()
db.refresh(db_resume)

# Later, it updates fields after LLM extraction
db_resume.name = parsed.name
db_resume.skills = json.dumps(parsed.skills)
db_resume.experience = json.dumps([exp.model_dump() for exp in parsed.experience])
db_resume.parsed_data = json.dumps(parsed.model_dump())
db.commit()
```

### 4. `backend/app/tools/db_tools.py` (Chatbot SQL Tools)
**Action:** Reads tables for the chat agent.
**Type:** SQLAlchemy ORM Pagination/Filters
```python
# Generic list records
items = db.query(model).all()

# Get Tender
t = db.query(Tender).filter(Tender.id == tender_id).first()

# Filter Resumes by text fields using LIKE (Primitive SQL Search)
query = db.query(Resume)
if min_experience is not None:
    query = query.filter(Resume.total_years_experience >= min_experience)
if skill:
    query = query.filter(Resume.skills.ilike(f"%{skill}%"))

resumes = query.limit(limit).all()
```

---

## D. Tables and Models Touched

1. **`resumes` (`Resume` model):**
   - **SQL Columns:** `id` (Int), `name` (Str), `email` (Str), `phone` (Str), `total_years_experience` (Float), `raw_text` (Text), `file_name` (Str), `parse_status` (Str), `created_at` (DateTime).
   - **JSON Blobs (Text):** `skills`, `experience`, `education`, `certifications`, `domain_expertise`, `parsed_data`, `field_resolution`, `standardized_skills`, `standardized_education`.
2. **`tenders` (`Tender` model):**
   - **SQL Columns:** `id`, `project_name`, `client`, `document_reference`, `project_duration`, `raw_text`, `file_name`, `parse_status`.
   - **JSON Blobs (Text):** `required_roles`, `eligibility_criteria`, `key_technologies`, `parsed_data`.
3. **`match_results` (`MatchResult` model):**
   - **SQL Columns:** `id`, `tender_id` (FK), `resume_id` (FK), `role_title`, `semantic_score`, `structured_score`, `final_score`, `llm_score`.
   - **JSON Blobs (Text):** `score_breakdown`, `strengths`, `concerns`, `scoring_criteria`.
4. **`chat_messages` (`ChatMessage` model):** Conversation history.
5. **`common_skills` / `common_education`:** Standardization alias tables.

---

## E. Upload Flow DB Writes

When a Resume or Tender is uploaded:
1. `smart_upload.py` creates a shallow record (`parse_status="processing"`) with the `.pdf` and raw extracted text.
2. The LangGraph extraction agent triggers (this is purely LLM/Python side).
3. Once the LLM returns the JSON schema, the router dumps lists and nested objects into stringified JSON via `json.dumps()` and updates the existing `Resume` or `Tender` row.
4. Concurrently, a dense vector embedding is saved to ChromaDB (`services/embedding.py`).

---

## F. Matching Flow DB Reads

> [!WARNING]
> Matching does **NOT** use SQL `WHERE` clauses to find candidates!

The DB Flow for matching is:
1. **Route (`/match/{tender_id}`):** Query SQLite for the full `Tender` object using `tender_id`. Parses JSON from `tender.required_roles`.
2. **Setup:** Queries SQLite for ALL resumes (`db.query(Resume).all()`) just to build an in-memory Python dictionary lookup map.
3. **Filtering:** Executes a call to vector db (`chromadb`) in `pre_filter` passing the role string to get the top `K` candidate IDs. No SQL constraints are applied here.
4. **Execution:** Takes those IDs, maps them to the Python dictionary populated in step 2. The LLM evaluates them.
5. **Save:** Clears old scores using `db.query(MatchResult).filter(...).delete()` and saves new ones with `db.add()`.

---

## G. Current Query Limitations

This is the most critical section for your natural-language-to-SQL agent.

1. **Anti-Pattern: Embedded JSON Objects.**
   - Complex nested data (like `project_value_cr`, `has_track_doubling_experience`, `client_type`) are stored inside the `parsed_data` column as stringified JSON.
   - **SQLite Limitations:** While SQLite has a `json_extract()` function, SQLAlchemy in your app is largely ignoring it. Searching for candidates with `project_value_cr > 100` natively in SQL is very hard because it's locked inside a text column.
2. **Anti-Pattern: Stringified Lists.**
   - Arrays like `skills`, `education`, and `domain_expertise` are saved as `"[\\"Skill A\\", \\"Skill B\\"]"` in a generic `Text` column. 
   - Operations like `WHERE list CONTAINS 'Python'` require awful `LIKE '%"Python"%'` queries which are prone to edge-case failures.
3. **Absence of Relational Joins:** 
   - A resume's "experiences" are not stored in a separate `Experience` table linked by a foreign key. They are a JSON dump. You cannot execute SQL like: `SELECT FROM Resumes r JOIN Experience e ON r.id = e.resume_id WHERE e.sector = 'Railways'`.
4. **Lack of Indexing on Filtered Items:** 
   - None of the AI-derived Boolean flags (e.g., `has_railway_experience`) have actual SQLite columns. They live inside `parsed_data`.

---

## H. What is Active vs Unused

- **Active:** `smart_upload.py`, `matching.py`, `match_agent.py`, `extraction_agent.py`, `backfill_resumes.py`.
- **Active but Flawed:** `backend/app/tools/db_tools.py` uses `Resume.skills.ilike(f"%{skill}%")` which is dangerous for stringified JSON arrays.
- **Unused/Dead:** Raw SQL strings via `execute("...")` (There are zero raw `.execute("SELECT...")` instances manually written in the codebase that bypass ORM).

---

## I. Final SQL Reality Report

The current repository uses SQLite via SQLAlchemy. True relational SQL is **barely being utilized**. The DB acts as a naive Key-Value store where the Values are just massive JSON strings representation of Pydantic models. 

**What SQL Currently Does:**
- Basic CRUD operations (fetch by ID, load entire list of strings, count rows).
- Saves and loads history of matching scores.

**What SQL Does NOT Do:**
- Filtering candidates.
- Searching for specific metadata (like "Find candidates with Bridge experience over 5 years").
- Querying nested document structures.

**Where to modify code for Natural Language SQL Generation:**
If you want another AI to write queries over this data, you have two choices:
1. **Refactor DB Models:** You must create separate tables (`projects`, `experiences`, `skills_linker`) so proper normalized SQL joins can be generated by an AI.
2. **Use SQLite JSON Functions:** The AI must generate queries utilizing `json_extract(parsed_data, '$.derived_profile.has_railway_experience') = 1`. You must instruct the next AI to treat SQLite as a document store and strictly use `json_extract`/`json_each` functions when building queries inside `db_tools.py`.

import logging
from openai import AsyncOpenAI
import chromadb
from app.config import settings

logger = logging.getLogger(__name__)

# OpenAI client for embeddings
openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

# 1. Custom OpenAI Embedding Function for ChromaDB
class OpenAIEmbeddingFunction(chromadb.EmbeddingFunction):
    def __call__(self, input: chromadb.Documents) -> chromadb.Embeddings:
        # Note: Chroma expects a sync call here, but our client is async.
        # However, for .query(query_texts=...) to work, this must be sync or handle it.
        # Alternatively, we'll avoid query_texts and do it manually in the tool.
        # BUT for collection initialization, providing THIS class with NO __call__ 
        # is enough to stop Chroma from defaulting to 384. 
        # Let's use a standard sync wrapper if needed, or stick to manual embedding.
        return [] # We won't use .query(query_texts=...)

# ChromaDB persistent client
chroma_client = chromadb.PersistentClient(path=settings.chroma_persist_dir)

# 2. Collections (No default embedding function to avoid 384 mismatch)
# We will always provide 'embeddings' or 'query_embeddings' manually.
resume_collection = chroma_client.get_or_create_collection(
    name="resumes",
    metadata={"hnsw:space": "cosine"},
)

tender_role_collection = chroma_client.get_or_create_collection(
    name="tender_roles",
    metadata={"hnsw:space": "cosine"},
)

resume_chunk_collection = chroma_client.get_or_create_collection(
    name="resume_chunks",
    metadata={"hnsw:space": "cosine"},
)

tender_chunk_collection = chroma_client.get_or_create_collection(
    name="tender_chunks",
    metadata={"hnsw:space": "cosine"},
)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts using OpenAI.

    Batches in groups of 100 to respect API limits.
    """
    all_embeddings = []
    batch_size = 100

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        # Truncate each text to avoid token limits
        batch = [t[:8000] for t in batch]

        response = await openai_client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
        )
        all_embeddings.extend([item.embedding for item in response.data])

    return all_embeddings


def store_resume_embedding(
    resume_id: int,
    embedding: list[float],
    metadata: dict,
) -> None:
    """Store a resume embedding in ChromaDB."""
    resume_collection.upsert(
        ids=[str(resume_id)],
        embeddings=[embedding],
        metadatas=[metadata],
        documents=[metadata.get("summary", "")],
    )


def delete_resume_embedding(resume_id: int) -> None:
    """Remove a resume embedding from ChromaDB."""
    try:
        resume_collection.delete(ids=[str(resume_id)])
        # Also clean up chunks
        results = resume_chunk_collection.get(where={"resume_id": resume_id})
        if results["ids"]:
            resume_chunk_collection.delete(ids=results["ids"])
    except Exception as e:
        logger.warning(f"Failed to delete embedding for resume {resume_id}: {e}")


def query_similar_resumes(
    query_embedding: list[float],
    n_results: int = 20,
) -> dict:
    """Query ChromaDB for resumes similar to the given embedding.

    Returns dict with keys: ids, distances, metadatas
    """
    count = resume_collection.count()
    if count == 0:
        return {"ids": [[]], "distances": [[]], "metadatas": [[]]}

    # Don't request more results than exist
    n = min(n_results, count)

    results = resume_collection.query(
        query_embeddings=[query_embedding],
        n_results=n,
    )
    return results


def store_tender_role_embedding(
    tender_id: int,
    role_index: int,
    embedding: list[float],
    metadata: dict,
) -> None:
    """Store a tender role embedding in ChromaDB."""
    doc_id = f"{tender_id}_role_{role_index}"
    tender_role_collection.upsert(
        ids=[doc_id],
        embeddings=[embedding],
        metadatas=[metadata],
        documents=[metadata.get("role_description", "")],
    )


def delete_tender_embeddings(tender_id: int) -> None:
    """Remove all role embeddings for a tender."""
    try:
        # Get all IDs for this tender
        results = tender_role_collection.get(
            where={"tender_id": tender_id},
        )
        if results["ids"]:
            tender_role_collection.delete(ids=results["ids"])
            
        # Clean up chunks
        chunk_results = tender_chunk_collection.get(where={"tender_id": tender_id})
        if chunk_results["ids"]:
            tender_chunk_collection.delete(ids=chunk_results["ids"])
    except Exception as e:
        logger.warning(f"Failed to delete embeddings for tender {tender_id}: {e}")


# --- Advanced Surgical RAG Functions ---

async def store_resume_chunks_vdb(resume_id: int, chunks: list[str]) -> None:
    """Batch store surgical chunks for a resume."""
    ids = [f"res_{resume_id}_idx_{i}" for i in range(len(chunks))]
    metadatas = [{"resume_id": resume_id, "index": i} for i in range(len(chunks))]
    
    # Generate embeddings in one batch for efficiency
    embeddings = await embed_texts(chunks)
    
    resume_chunk_collection.upsert(
        ids=ids,
        embeddings=embeddings,
        metadatas=metadatas,
        documents=chunks
    )

def query_resume_chunks(resume_id: int, query_embedding: list[float], n_results: int = 5) -> dict:
    """Surgically query chunks for a specific resume."""
    return resume_chunk_collection.query(
        query_embeddings=[query_embedding],
        where={"resume_id": resume_id},
        n_results=n_results
    )

def query_global_resume_chunks(query_embedding: list[float], n_results: int = 10) -> dict:
    """Query across ALL resume chunks in the database for board cross-document search."""
    return resume_chunk_collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results
    )

async def query_resume_chunks_keyword(resume_id: int, keyword: str, n_results: int = 5) -> dict:
    """Surgically query chunks for a specific resume using EXACT KEYWORD matching in ChromaDB.
    Fixes dimension mismatch by AVOIDING internal query_texts.
    """
    # We generate a dummy embedding of the correct dimension (1536) 
    # to satisfy Chroma's .query() requirement while relying on the metadata filter.
    dummy_embedding = [0.0] * 1536
    
    return resume_chunk_collection.query(
        query_embeddings=[dummy_embedding],
        where={"resume_id": resume_id},
        where_document={"$contains": keyword},
        n_results=n_results
    )

async def store_tender_chunks_vdb(tender_id: int, chunks: list[str]) -> None:
    """Batch store surgical chunks for a tender."""
    ids = [f"tnd_{tender_id}_idx_{i}" for i in range(len(chunks))]
    metadatas = [{"tender_id": tender_id, "index": i} for i in range(len(chunks))]
    
    embeddings = await embed_texts(chunks)
    
    tender_chunk_collection.upsert(
        ids=ids,
        embeddings=embeddings,
        metadatas=metadatas,
        documents=chunks
    )

def query_tender_chunks(tender_id: int, query_embedding: list[float], n_results: int = 4) -> dict:
    """Surgically query chunks for a specific tender."""
    return tender_chunk_collection.query(
        query_embeddings=[query_embedding],
        where={"tender_id": tender_id},
        n_results=n_results
    )

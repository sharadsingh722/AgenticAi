"""
app/services/chunk_manager.py

Unified Surgical Chunking Engine for the Resume-Tender RAG system.
Optimized for 2000-character dynamic scaling and metadata injection.
"""
import re
import logging
import numpy as np
from typing import List, Optional
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class BGEModelSingleton:
    """Lazy-loader for the local embedding model."""
    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            logger.info("Initializing BAAI/bge-base-en-v1.5 locally...")
            cls._model = SentenceTransformer('BAAI/bge-base-en-v1.5')
        return cls._model

class ChunkManager:
    """Entry point for all document chunking operations."""

    @classmethod
    def create_chunks(cls, text: str, is_resume: bool, **kwargs) -> List[str]:
        """
        Orchestrates Advanced Surgical Chunking.
        - Dynamic Scaling (up to 2000 chars)
        - Metadata Injection (Source, Section, Candidate)
        - Table Header Restoration
        """
        logger.info(f"Starting Metadata-Enriched Chunking for {'Resume' if is_resume else 'Tender'}...")
        
        size = kwargs.get("chunk_size", 2500) 
        max_size = 3000
        overlap = kwargs.get("chunk_overlap", 250)
        source_name = kwargs.get("file_name", "Unknown File")
        
        # 1. Primary Split by Markdown Hierarchy
        headers = [("#", "H1"), ("##", "H2"), ("###", "H3"), ("####", "H4")]
        h_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers)
        raw_splits = h_splitter.split_text(text)
        
        # 1.5 AGGREGATE SMALL SPLITS
        # Combine tiny sections (like consecutive small tables and headers) into meaningful blocks
        initial_splits = []
        current_aggregated_text = ""
        current_combined_metadata = {}
        target_min_size = 2000  # Increased to keep entire large projects together
        
        for split in raw_splits:
            content = split.page_content.strip()
            if not content: continue
                
            # Build section breadcrumb for this split
            meta = split.metadata
            cur_sections = " > ".join([meta[h] for h in ["H1", "H2", "H3", "H4"] if h in meta])
            
            fragment = f"[SECTION: {cur_sections}]\n{content}" if cur_sections else content
            
            if len(current_aggregated_text) + len(fragment) < target_min_size:
                # Keep joining
                current_aggregated_text += ("\n\n" + fragment) if current_aggregated_text else fragment
                current_combined_metadata.update(meta)
            else:
                # Push the aggregated block and start new
                if current_aggregated_text:
                    class DummySplit:
                        def __init__(self, c, m):
                            self.page_content = c
                            self.metadata = m
                    initial_splits.append(DummySplit(current_aggregated_text, current_combined_metadata))
                
                current_aggregated_text = fragment
                current_combined_metadata = meta.copy()
                
        # Push remainder
        if current_aggregated_text:
            class DummySplit_Final:
                def __init__(self, c, m):
                    self.page_content = c
                    self.metadata = m
            initial_splits.append(DummySplit_Final(current_aggregated_text, current_combined_metadata))

        final_chunks = []
        last_table_header = None
        
        for split in initial_splits:
            content = split.page_content
            metadata = split.metadata
            
            # 2. Table Header Tracking
            if '|' in content and '---' in content:
                match = re.search(r'(\|.*\|\n\|[- :|]+\|)', content)
                if match: last_table_header = match.group(1)

            # 3. Dynamic Scaling Decision
            if len(content) < max_size:
                sub_chunks = [content]
            else:
                if is_resume:
                    sub_chunks = cls._split_semantically(content, size, threshold=0.55)
                else:
                    sub_chunks = cls._split_recursively(content, size, overlap)
            
            # 4. Contextual Enrichment & Metadata Injection
            for chunk in sub_chunks:
                # Restore table context if missing
                if chunk.strip().startswith('|') and last_table_header:
                    if last_table_header.split('\n')[0] not in chunk:
                        chunk = f"{last_table_header}\n{chunk}"
                
                # Build file header
                context_header = f"[FILE: {source_name}]"
                
                final_content = f"{context_header}\n\n{chunk}"
                final_chunks.append(cls._final_clean(final_content))
                
        return [c for c in final_chunks if len(c) > 30]

    @classmethod
    def _split_semantically(cls, text: str, target_size: int, threshold: float) -> List[str]:
        """Surgically splits a large section using BGE topic-shift detection."""
        # Split by sentences, avoid splitting tables
        sentences = re.split(r'(?<!\|)(?<=[.!?]) +(?![^|]*\|)', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences: return []
        
        model = BGEModelSingleton.get_model()
        embeddings = model.encode(sentences, normalize_embeddings=True)
        
        chunks = []
        current = [sentences[0]]
        current_len = len(sentences[0])
        max_limit = 2000
        
        for i in range(len(sentences) - 1):
            similarity = np.dot(embeddings[i], embeddings[i+1])
            if (similarity < threshold and current_len > target_size // 2) or current_len > max_limit:
                chunks.append(" ".join(current))
                current = [sentences[i+1]]
                current_len = len(sentences[i+1])
            else:
                current.append(sentences[i+1])
                current_len += len(sentences[i+1]) + 1
        
        if current:
            chunks.append(" ".join(current))
        return chunks

    @classmethod
    def _split_recursively(cls, text: str, size: int, overlap: int) -> List[str]:
        """Recursive split for large sections."""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=size, chunk_overlap=overlap, keep_separator=True
        )
        return splitter.split_text(text)

    @staticmethod
    def _final_clean(content: str) -> str:
        """Removes hidden page markers and fixes fragmented bolding."""
        text = re.sub(r'<!-- PAGE_(START|END)_\d+ -->', '', content).strip()
        if text.count('**') % 2 != 0: text += '**'
        return text

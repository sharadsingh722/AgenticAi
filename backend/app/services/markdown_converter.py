import os
import pymupdf4llm
import logging
from typing import List, Optional
from app.services.logical_merger import LogicalMerger, DocumentType

logger = logging.getLogger(__name__)

class MarkdownConverter:
    """
    Transforms PDF/TXT into high-fidelity Markdown. 
    Injects page-tracking markers and applies structural healing.
    """
    
    @staticmethod
    def convert(
        file_path: str, 
        doc_type: DocumentType = DocumentType.RFP
    ) -> str:
        """
        Converts a document to Markdown with Marker Injection and Logical Merging.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        
        try:
            full_markdown = ""
            
            # --- PHASE 1: RAW INGESTION ---
            if ext == ".pdf":
                # Convert page-by-page to inject high-fidelity markers
                import fitz
                with fitz.open(file_path) as doc:
                    for p_idx in range(len(doc)):
                        # Pymupdf4llm context: we use simple conversion per page
                        page_md = pymupdf4llm.to_markdown(file_path, pages=[p_idx])
                        full_markdown += f"\n<!-- PAGE_START_{p_idx} -->\n{page_md}\n<!-- PAGE_END_{p_idx} -->\n"
            
            elif ext == ".txt":
                with open(file_path, "r", encoding="utf-8") as f:
                    full_markdown = f"\n<!-- PAGE_START_0 -->\n{f.read()}\n<!-- PAGE_END_0 -->\n"
            
            else:
                # Handle images or other types if necessary, for now fallback to basic text or error
                raise ValueError(f"Unsupported file type: {ext}")

            # --- PHASE 2: STRUCTURAL HEALING ---
            logger.info(f"Applying Logical Merger for {doc_type.value}...")
            return LogicalMerger.merge_and_clean(full_markdown, doc_type=doc_type)

        except Exception as e:
            logger.error(f"Markdown conversion failed: {str(e)}")
            raise e

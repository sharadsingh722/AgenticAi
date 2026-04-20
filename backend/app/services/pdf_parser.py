import os
import hashlib
import logging
from typing import Optional, List, Dict, Any
import pdfplumber
import fitz  # PyMuPDF
from io import BytesIO

logger = logging.getLogger(__name__)


def extract_candidate_images_from_pdf(pdf_bytes: bytes, limit: int = 10) -> List[Dict[str, Any]]:
    """Extract candidate images from all pages of a PDF.
    
    Filters by size and aspect ratio and scores them.
    Returns a list of dicts with 'image', 'ext', 'width', 'height', 'score'.
    """
    candidates = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_area = page.rect.width * page.rect.height
            images = page.get_images(full=True)
            
            for img_info in images:
                xref = img_info[0]
                base_image = doc.extract_image(xref)
                if not base_image:
                    continue
                
                width = base_image.get("width", 0)
                height = base_image.get("height", 0)
                
                # Minimum size filter
                if width < 30 or height < 30:
                    continue
                
                area = width * height
                # Ignore background full-page scans (usually > 70% of page area)
                if area > page_area * 0.7:
                    continue
                
                aspect_ratio = width / height
                # We prefer square (1:1) or standard portrait (3:4 = 0.75) shapes
                # Penalize very wide/thin images commonly used for logos
                shape_score = 1.0
                if 0.5 <= aspect_ratio <= 1.5:
                    shape_score = 3.0 # Strong portrait/square preference
                elif aspect_ratio > 3.0 or aspect_ratio < 0.3:
                    shape_score = 0.1 # Very likely a logo or divider
                
                # Final score combines area and shape
                score = area * shape_score
                
                candidates.append({
                    "image": base_image["image"],
                    "ext": base_image["ext"],
                    "width": width,
                    "height": height,
                    "score": score
                })
            
            # If we've found many candidates across several pages, stop to balance coverage vs speed
            if len(candidates) >= limit and page_num >= 10:
                break
        doc.close()
    except Exception as e:
        logger.error(f"Failed to extract images from PDF: {e}")

    return sorted(candidates, key=lambda x: x["score"], reverse=True)


def extract_photo_from_pdf(pdf_bytes: bytes, upload_dir: str) -> Optional[str]:
    """Extract the best candidate image that looks like a portrait and save it.
    
    Returns the filename if found and saved, None otherwise.
    """
    candidates = extract_candidate_images_from_pdf(pdf_bytes, limit=15)
    if not candidates:
        return None

    try:
        # Take the top-scoring candidate
        candidate = candidates[0]
        image_bytes = candidate["image"]
        ext = candidate["ext"]

        # Save the image
        os.makedirs(os.path.join(upload_dir, "photos"), exist_ok=True)
        img_hash = hashlib.md5(image_bytes).hexdigest()[:12]
        filename = f"{img_hash}.{ext}"
        filepath = os.path.join(upload_dir, "photos", filename)

        with open(filepath, "wb") as f:
            f.write(image_bytes)

        return filename
    except Exception as e:
        logger.error(f"Failed to save extracted photo: {e}")
        return None


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF file using pdfplumber.

    Processes every page and concatenates text with page separators.
    Returns empty string if no text could be extracted (e.g., scanned PDF).
    """
    text_parts = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    return "\n\n".join(text_parts)


def extract_text_with_tables(pdf_bytes: bytes) -> str:
    """Extract text and tables from PDF, with better handling of tabular data."""
    text_parts = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            # Try extracting tables first
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    if table:
                        for row in table:
                            if row:
                                cleaned = [str(cell).strip() if cell else "" for cell in row]
                                text_parts.append(" | ".join(cleaned))
                text_parts.append("")  # separator

            # Also get regular text
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    return "\n\n".join(text_parts)

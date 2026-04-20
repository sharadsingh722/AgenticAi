import sys
import os
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.services.pdf_parser import extract_candidate_images_from_pdf, extract_photo_from_pdf

def test_imports():
    print("Testing imports and function signatures...")
    # Dummy bytes
    dummy_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
    
    try:
        candidates = extract_candidate_images_from_pdf(dummy_pdf)
        print(f"extract_candidate_images_from_pdf executed. Candidates found: {len(candidates)}")
        
        # Test extract_photo_from_pdf (it should return None for dummy bytes)
        photo = extract_photo_from_pdf(dummy_pdf, "./backend/data/uploads")
        print(f"extract_photo_from_pdf executed. Photo: {photo}")
        
    except Exception as e:
        print(f"Test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_imports()

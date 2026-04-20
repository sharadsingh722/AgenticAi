import fitz
import sys

def debug_pdf(pdf_path):
    print(f"DEBUGGING: {pdf_path}")
    doc = fitz.open(pdf_path)
    print(f"Total Pages: {len(doc)}")
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        images = page.get_images(full=True)
        print(f"\n--- Page {page_num + 1} ---")
        print(f"Found {len(images)} total image objects.")
        
        for i, img_info in enumerate(images):
            xref = img_info[0]
            base_image = doc.extract_image(xref)
            if not base_image:
                print(f"  [{i}] XREF {xref}: Could not extract image data.")
                continue
            
            w = base_image.get("width", 0)
            h = base_image.get("height", 0)
            ext = base_image.get("ext", "png")
            aspect = max(w, h) / max(min(w, h), 1)
            
            print(f"  [{i}] XREF {xref}: {w}x{h} ({ext}), Aspect: {aspect:.2f}")
    
    doc.close()

if __name__ == "__main__":
    # Finding the filename again to be sure
    import os
    resumes_dir = "./backend/data/uploads/resumes"
    files = sorted([f for f in os.listdir(resumes_dir) if f.endswith(".pdf")], 
                   key=lambda f: os.path.getmtime(os.path.join(resumes_dir, f)), 
                   reverse=True)
    if files:
        debug_pdf(os.path.join(resumes_dir, files[0]))
    else:
        print("No resumes found.")

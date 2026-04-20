# Add current directory to sys.path first to avoid conflicts with global 'app' modules
import os
import sys
current_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app.agents.extraction_agent import _extract_education_from_qualification_section
from app.schemas import ResumeParseResult

def test_regex_extraction():
    print("Testing Regex Extraction...")
    
    # Case 1: Infracon style
    text1 = """
    QUALIFICATION DETAILS
    Graduate/Degree BE Civil Engineering, Delhi University, 2010
    Post Graduate M.Tech Structure, IIT Delhi, 2012
    EXPERIENCE DETAILS
    """
    res1 = _extract_education_from_qualification_section(text1)
    print(f"Case 1 (Infracon): {res1}")
    assert any("BE Civil Engineering" in r for r in res1)
    assert any("M.Tech" in r for r in res1)

    # Case 2: Generic text (No header)
    text2 = """
    I have a B.Tech in Computer Science from Amity University and an MBA in Finance.
    Education:
    Bachelor of Technology in CS, 2015
    """
    res2 = _extract_education_from_qualification_section(text2)
    print(f"Case 2 (Generic): {res2}")
    assert any("B.Tech" in r for r in res2)
    assert any("MBA" in r for r in res2)

    # Case 3: Messy OCR
    text3 = """
    Academic Credentials:
    Diploma in Civil Engineering - Year 2005
    Ph.D in Geology from University of Mumbai.
    """
    res3 = _extract_education_from_qualification_section(text3)
    print(f"Case 3 (Messy): {res3}")
    assert any("Diploma" in r for r in res3)
    assert any("Ph.D" in r for r in res3)
    assert any("University of Mumbai" in r for r in res3)

def test_sanitization():
    print("\nTesting Sanitization Logic...")
    # Mocking what the agent might return
    data = {
        "name": "Test User",
        "education": "B.Tech Civil", # Should be list
        "skills": "Python, Java", # Should be list
        "field_resolution": None # Should be dict
    }
    
    # Simulating the sanitization logic in llm_extractor.py
    if not isinstance(data, dict):
        raise ValueError("Not a dict")
    
    data.setdefault("name", "Unknown")
    list_fields = ["skills", "education", "certifications", "domain_expertise", "experience"]
    for field in list_fields:
        if field in data and not isinstance(data[field], list):
            val = data[field]
            data[field] = [val] if val else []
        elif field not in data:
            data[field] = []

    if "field_resolution" not in data or not isinstance(data["field_resolution"], dict):
        data["field_resolution"] = {
            "skills_source": {},
            "education_source": {},
            "domain_source": {},
        }

    # Validate with Pydantic
    parsed = ResumeParseResult(**data)
    print(f"Sanitized Data: {parsed.model_dump(include={'name', 'education', 'skills', 'field_resolution'})}")
    assert isinstance(parsed.education, list)
    assert isinstance(parsed.skills, list)
    assert isinstance(parsed.field_resolution.skills_source, dict)

if __name__ == "__main__":
    try:
        test_regex_extraction()
        test_sanitization()
        print("\nALL TESTS PASSED!")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

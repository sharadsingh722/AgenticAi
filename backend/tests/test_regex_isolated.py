import re

def _extract_education_from_qualification_section_LOGIC(raw_text: str) -> list[str]:
    """Parse common Infracon qualification tables and generic education patterns without an API call."""
    results = []

    def add_unique(value: str) -> None:
        clean = re.sub(r"\s+", " ", value).strip(" ,.-")
        if clean and clean not in results:
            results.append(clean)

    # 1. Look for specific Infracon-style "QUALIFICATION DETAILS" section
    match = re.search(
        r"QUALIFICATION DETAILS(.*?)(?:COMPANIES DETAILS|DETAILED WORK DETAILS|EXPERIENCE|$)",
        raw_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    
    section = ""
    if match:
        section = match.group(1)
        # Clean up timestamps and URLs often found in Infracon exports
        section = re.sub(r"https?://\S+", " ", section)
        section = re.sub(r"\b\d{1,2}/\d{1,2}/\d{4},?\s+\d{1,2}:\d{2}\s*[APMapm]{2}\b", " ", section)
        section = re.sub(r"\s+", " ", section).strip()

    # 2. Extract from section using keywords
    if section:
        chunks = list(
            re.finditer(
                r"(Graduate/Degree|Post Graduate|Diploma|High School|Schooling)\s+(.*?)(?=Graduate/Degree|Post Graduate|Diploma|High School|Schooling|$)",
                section,
                flags=re.IGNORECASE,
            )
        )
        for chunk in chunks:
            level = chunk.group(1).strip()
            body = chunk.group(2).strip()
            year_match = re.search(r"((?:19|20)\d{2})", body)
            year = year_match.group(1) if year_match else None
            body_lower = body.lower()

            # Generic Level + Body combination
            value = f"{level} {body}".strip()
            add_unique(value)

    # 3. Broad search for common degree patterns if we didn't find much
    if len(results) < 1:
        # Common degree regex patterns
        degree_patterns = [
            r"\b(B\.?E\.?|B\.?Tech\.?|Bachelor of Technology|Bachelor of Engineering)\s+(?:in\s+)?([A-Za-z\s]{3,30})",
            r"\b(M\.?E\.?|M\.?Tech\.?|Master of Technology|Master of Engineering)\s+(?:in\s+)?([A-Za-z\s]{3,30})",
            r"\b(B\.?Sc\.?|Master of Science|M\.?Sc\.?)\s+(?:in\s+)?([A-Za-z\s]{3,30})",
            r"\b(B\.?A\.?|M\.?A\.?|Bachelor of Arts|Master of Arts)\s+(?:in\s+)?([A-Za-z\s]{3,30})",
            r"\b(MBA|M\.?B\.?A\.?|Master of Business Administration)\s+(?:in\s+)?([A-Za-z\s]{3,30})",
            r"\b(Ph\.?D\.?|Doctor of Philosophy)\b",
            r"\b(Diploma)\s+(?:in\s+)?([A-Za-z\s]{3,30})",
        ]
        
        for pattern in degree_patterns:
            for m in re.finditer(pattern, raw_text, flags=re.IGNORECASE):
                groups = m.groups()
                degree = groups[0]
                spec = groups[1] if len(groups) > 1 and groups[1] else ""
                val = f"{degree} {spec}".strip()
                # Find near university if possible (within 100 chars)
                context = raw_text[max(0, m.start() - 100):min(len(raw_text), m.end() + 100)]
                univ_match = re.search(r"(?:University|Institute|College) of ([A-Za-z\s]{3,50})", context, flags=re.IGNORECASE)
                if univ_match:
                    val += f", {univ_match.group(0)}"
                add_unique(val)

    return results

def test_regex_extraction():
    print("Testing Regex Extraction (Isolated)...")
    
    # Case 1: Infracon style
    text1 = """
    QUALIFICATION DETAILS
    Graduate/Degree BE Civil Engineering, Delhi University, 2010
    Post Graduate M.Tech Structure, IIT Delhi, 2012
    EXPERIENCE DETAILS
    """
    res1 = _extract_education_from_qualification_section_LOGIC(text1)
    print(f"Case 1 (Infracon): {res1}")
    assert any("Graduate/Degree BE Civil Engineering" in r for r in res1)
    assert any("Post Graduate M.Tech Structure" in r for r in res1)

    # Case 2: Generic text (No header) - This should trigger the broad search
    text2 = """
    I have a B.Tech in Computer Science from Amity University and an MBA in Finance.
    Education:
    Bachelor of Technology in CS, 2015
    """
    res2 = _extract_education_from_qualification_section_LOGIC(text2)
    print(f"Case 2 (Generic): {res2}")
    assert any("B.Tech" in r for r in res2)
    assert any("MBA" in r for r in res2)

    # Case 3: Messy OCR
    text3 = """
    Academic Credentials:
    Diploma in Civil Engineering - Year 2005
    Ph.D in Geology from University of Mumbai.
    """
    res3 = _extract_education_from_qualification_section_LOGIC(text3)
    print(f"Case 3 (Messy): {res3}")
    assert any("Diploma" in r for r in res3)
    assert any("Ph.D" in r for r in res3)
    assert any("University of Mumbai" in r for r in res3)

if __name__ == "__main__":
    try:
        test_regex_extraction()
        print("\nALL ISOLATED TESTS PASSED!")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

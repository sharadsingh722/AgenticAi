"""Prompts for resume extraction."""

RESUME_STRUCTURE_PROMPT = """Analyze this resume document and identify its major sections.
Return a JSON object with:
- "sections": list of {{"name": "section name", "keywords": ["key phrases to find this section"]}}
- "summary": one-line description of the document

Document text (first 5000 chars):
{text_sample}"""

RESUME_DEEP_EXTRACT_PROMPT = """You are an expert resume parser for a tender–resume matching system.

Your task is to extract structured information from the resume and return ONLY valid JSON matching the exact schema provided below.

Important goals:

* Extract maximum useful information from the resume
* Preserve factual accuracy
* Do not hallucinate
* If a value is missing, use safe defaults
* Prefer structured extraction over vague summaries
* Normalize values where possible

Return ONLY valid JSON.
Do not add markdown.
Do not add explanation text.
Do not wrap in code fences.

Schema to return:

{{
"name": "Unknown",
"email": null,
"phone": null,
"skills": [],
"experience": [
{{
"company": "",
"role": "",
"duration": "",
"description": "",
"sector": "",
"subsector": "",
"client_type": "",
"components": [],
"project_value_cr": 0.0,
"length_km": 0.0,
"location": ""
}}
],
"education": [],
"certifications": [],
"total_years_experience": 0.0,
"domain_expertise": [],
"field_resolution": {{
"skills_source": {{}},
"education_source": {{}},
"domain_source": {{}}
}},
"standardized_skills": [],
"standardized_education": [],
"derived_profile": {{
"has_railway_experience": false,
"has_epc_experience": false,
"has_track_doubling_experience": false,
"has_new_line_experience": false,
"has_gauge_conversion_experience": false,
"has_electrification_experience": false,
"has_signalling_experience": false,
"has_telecommunication_experience": false,
"has_bridge_or_structure_experience": false,
"has_survey_experience": false,
"has_design_experience": false,
"has_testing_commissioning_experience": false,
"has_government_project_experience": false,
"has_public_sector_experience": false,
"has_large_scale_project_experience": false,
"max_project_value_cr": 0.0,
"max_project_length_km": 0.0,
"railway_project_count": 0,
"epc_project_count": 0,
"relevant_project_count": 0
}}
}}

Extraction rules:

1. Basic identity

* "name": candidate full name if clearly available, otherwise "Unknown"
* "email": valid email or null
* "phone": valid phone or null

2. Skills

* Extract every meaningful skill mentioned anywhere in the resume
* Include technical skills, tools, software, methodologies, domain capabilities, execution-related skills
* Keep "skills" as raw extracted skill phrases
* Keep "standardized_skills" as normalized/canonical forms where possible
* Examples of standardized values:
  * "MS Excel" -> "excel"
  * "Auto CAD" -> "autocad"
  * "Railway Electrification" -> "railway electrification"
  * "Signalling & Telecom" -> "signalling"
* Do not invent skills

3. Experience
   For each experience item or major project, extract:

* "company": employer/client/organization name if available
* "role": designation or project role
* "duration": exact textual duration/date range if available
* "description": concise factual summary from the resume
* "sector": classify into one of these when possible:
  * "railway"
  * "metro"
  * "highway"
  * "bridge"
  * "tunnel"
  * "public_infrastructure"
  * "construction"
  * "epc"
  * "power"
  * "telecom"
  * "it"
  * "general"
  * "" if unclear
* "subsector": more specific classification if visible, such as:
  * "track_doubling"
  * "new_line"
  * "gauge_conversion"
  * "electrification"
  * "signalling"
  * "bridge_construction"
  * "road_construction"
  * "building_construction"
  * "qa_qc"
  * "planning"
  * "general"
  * "" if unclear
* "client_type": classify as one of:
  * "government"
  * "public_sector"
  * "private"
  * "" if unclear
* "components": extract a list of scope/work components mentioned in that role/project

Allowed component values:
* "survey"
* "investigation"
* "design"
* "earthwork"
* "formation"
* "ballast"
* "track_work"
* "doubling"
* "new_line"
* "gauge_conversion"
* "electrification"
* "overhead_equipment"
* "substation"
* "signalling"
* "telecommunication"
* "bridges"
* "structures"
* "buildings"
* "testing"
* "commissioning"
* "qa_qc"
* "planning"
* "execution"
* "maintenance"

Rules for project_value_cr:
* Extract numeric value in crore if explicitly mentioned or can be reliably converted
* Example:
  * "Rs. 120 Cr" -> 120.0
  * "INR 45 crore" -> 45.0
* If only lakh is given, convert to crore
* If ambiguous, missing, or unreliable, use 0.0

Rules for length_km:
* Extract numeric project length in km if explicitly mentioned
* Example:
  * "22 km rail corridor" -> 22.0
* If missing or unclear, use 0.0

Rules for location:
* Extract city/state/country/project region if clearly available
* Otherwise use ""

4. Education
* Keep "education" as raw textual entries
* Keep "standardized_education" as normalized values when possible, like:
  * "B.Tech Civil Engineering"
  * "Diploma Mechanical Engineering"
  * "MBA"
* Extract all degrees, diplomas, major educational qualifications

5. Certifications
* Extract all certifications, licenses, trainings, qualification credentials if mentioned
* Do not confuse education with certifications

6. Total years of experience
* Estimate total PROFESSIONAL tenure (full-time work) only.
* EXCLUSION RULE: Do NOT count academic projects, university projects, or internships towards the numeric total_years_experience for students/freshers.
* EXCLUSION RULE: Do NOT count the duration of a degree (e.g. "MCA - 2 years") as work experience.
* For freshers with only projects/internships, use 0.0 or a small fraction (e.g. 0.3) only if substantial industrial training exists.
* Use numeric float format only. (e.g., 0.0 for students).

7. Domain expertise
* Extract higher-level professional domains from the whole resume.
* FOR STUDENTS/FRESHERS: Tag them with domains corresponding to their degree specialization and projects (e.g., "IT", "Software Development", "Data Science", "Civil Construction").
* Examples: "railway", "epc", "infrastructure", "civil construction", "electrification", "signalling", "project management", "it", "software development".
* Do not add irrelevant generic buzzwords.

8. Field resolution
   This object should record lightweight traceability:
* "skills_source": map standardized skill -> short raw phrase from resume
* "education_source": map standardized education -> short raw phrase from resume
* "domain_source": map domain_expertise item -> short evidence phrase from resume
  Keep these maps concise.

9. Derived profile
   Populate the derived_profile based ONLY on extracted experience and resume evidence.
Set booleans to true only if evidence exists:
* has_railway_experience
* has_epc_experience
* has_track_doubling_experience
* has_new_line_experience
* has_gauge_conversion_experience
* has_electrification_experience
* has_signalling_experience
* has_telecommunication_experience
* has_bridge_or_structure_experience
* has_survey_experience
* has_design_experience
* has_testing_commissioning_experience
* has_government_project_experience
* has_public_sector_experience
* has_large_scale_project_experience

Derived numeric rules:
* max_project_value_cr = maximum extracted project_value_cr
* max_project_length_km = maximum extracted length_km
* railway_project_count = number of experience items clearly related to railway
* epc_project_count = number of experience items clearly related to EPC
* relevant_project_count = number of experience items materially relevant to infrastructure / tender-style matching

Rule for has_large_scale_project_experience:
* true if any project_value_cr is significant, such as >= 50 crore
* or length_km is significant, such as >= 10 km
* otherwise false

Important constraints:
* Never hallucinate company names, numbers, certifications, or project metrics
* Use empty string, empty array, 0.0, false, or null when data is not available
* Maintain exact JSON structure
* Return only JSON

Now parse this resume:
{text}
"""

RESUME_VERIFICATION_PROMPT = """Verify this extracted resume data against the source text. List any issues:

Extracted:
- Name: {name}
- Skills ({skill_count}): {skills_snippet}...
- Experience entries: {exp_count}
- Total years: {years}
- Education: {education}

Source text (first 8000 chars):
{raw_snippet}

Return JSON: {{"issues": ["issue1", "issue2"], "is_valid": true/false}}
If no issues, return {{"issues": [], "is_valid": true}}"""

RESUME_FIX_ISSUES_PROMPT = """The following extraction had issues that need fixing:

Issues found:
{issues_json}

Current extracted data:
{data_json}

Source document (first 15000 chars):
{raw_snippet}

Fix ONLY the identified issues. Ensure you maintain the exact JSON schema. Return the complete corrected JSON data."""

RESUME_EDU_FALLBACK_PROMPT = """You are extracting ONLY education details from noisy OCR resume text.

Return valid JSON only in this schema:
{{
  "education": ["qualification 1", "qualification 2"],
  "field_resolution": {{
    "education": [
      {{
        "raw_value": "original extracted education/qualification",
        "normalized_value": "lowercase cleaned education value",
        "common_table_match": null,
        "resolution_method": "new",
        "final_common_value": "short_lowercase_underscore_value"
      }}
    ]
  }}
}}

Rules:
- Extract only qualifications explicitly supported by the text.
- OCR may be messy or table-like. Reconstruct obvious spacing if needed.
- If the text says "Graduate/Degree" plus branch + university + year, keep that wording.
- Do not invent BTech/BE/MTech unless the text explicitly supports it.
- If nothing reliable is present, return an empty list.

Resume snippet:
{context}
"""

RESUME_EDU_CLASSIFIER_PROMPT = """Classify this academic qualification into exactly one category.

Qualification: {raw_value}

Categories:
- graduate      : Bachelor's level (B.E., B.Tech, BCA, BSc, BA, BBA, AMIE, and equivalents)
- postgraduate  : Master's level (M.Tech, M.E., MSc, MBA, MCA, Post-Graduate Diploma after graduation)
- phd           : Doctorate (Ph.D., D.Sc., etc.)
- diploma       : Polytechnic or after-10th diploma (NOT post-grad diploma)
- highschool    : Class X, Class XII, Secondary / Senior Secondary
- other         : If none of the above applies

Reply with ONLY the single category word. No explanation."""

RESUME_NORMALIZER_PROMPT = """You are an AI normalization engine mapping messy '{category}' data to clean system keys.

Your job is to read a raw extracted value and suggest a clean, normalized, underscore-separated database key for it.

Raw Value: {raw_value}

Rules:
1. Use lowercase, alphanumeric characters, and underscores only.
2. Shorten verbose phrases while keeping the semantic meaning (e.g. "Bachelor of Engineering in Civil" -> "btech_civil").
3. For education: prioritize degree + branch (e.g., "mtech_structural", "bsc_geology", "diploma_civil").
4. For skills: just clean the name (e.g. "MS Excel 2018" -> "excel", "Auto-CAD" -> "autocad").
5. Return ONLY the normalized string. No quotes, no explanation.
"""

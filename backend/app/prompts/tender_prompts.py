"""Prompts for tender extraction."""

TENDER_DEEP_EXTRACT_PROMPT = """You are an expert tender/RFP document parser. Extract ALL structured requirements.

Return valid JSON matching this EXACT schema:
{{
  "project_name": "Project Name",
  "client": "Client/Organization or null",
  "document_reference": "RFP/Tender reference number or null",
  "document_date": "YYYY-MM-DD or null",
  "required_roles": [
    {{
      "role_title": "Role Name",
      "min_experience": 5,
      "required_skills": ["skill1"],
      "required_certifications": ["cert1"],
      "required_domain": ["domain1"],
      "preferred_components": ["bridge", "viaduct"],
      "min_project_value_cr": 100.0,
      "client_type_preference": "government"
    }}
  ],
  "eligibility_criteria": ["criterion1"],
  "project_duration": "e.g. 12 months or null",
  "key_technologies": ["tech1"]
}}

IMPORTANT:
- required_roles: This is the MOST CRITICAL field. Search the ENTIRE document thoroughly for personnel requirements:
  * Look for sections titled: "Team Composition", "Key Personnel", "Manpower Requirements", "Team Profiles", "Snap-shot of Team Deployment", "Resource Deployment", "Human Resources", "Staffing", "Personnel"
  * Look in TABLES that list roles with qualifications, experience, skills
  * Look for role titles like: Project Manager, Team Leader, System Administrator, DBA, Developer, Engineer, Domain Expert, etc.
  * For EACH role found, extract the specific skills, experience, certifications, and domain mentioned FOR THAT ROLE
  * If skills are mentioned generically for the project (e.g., in Scope of Work or Technology sections), assign them to the most relevant roles
  * required_skills should include BOTH technical skills AND soft skills mentioned for each role
  * required_domain should reflect the industry context (IT, infrastructure, government, etc.)
  * preferred_components should extract specific infrastructure elements (e.g., elevated corridor, tunneling, metro, highway) required for the role.
  * min_project_value_cr: Extract any mention of minimum project value handled by the key personnel, convert to Crores. Default to 0.0 if not specified.
  * client_type_preference: Extract if the role requires experience with specific clients (e.g., PSU, Government, Private).
- document_reference: Look for RFP No., Tender No., NIT No., Letter No., Reference No.
- key_technologies: Extract ALL technologies mentioned anywhere in the document
- If the tender mentions technologies like AI, GIS, Cloud, etc. in scope but doesn't assign them to specific roles, still list them in key_technologies AND assign to relevant technical roles
- CRITICAL: If the tender describes a team deployment table with generic categories (e.g., "Project Management", "Application Design", "Operations & Maintenance"), expand these into SPECIFIC roles. For example:
  * "Project Management" → Project Manager
  * "Application Design, Development" → Application Development Expert
  * "Operations & Maintenance" → System/Network Administrator, Database Administrator
  * "Capacity Building" → Capacity Building/Change Management Expert
  * If the scope mentions GIS, Drones, AI → add Domain Expert roles
  * For each inferred role, populate required_skills/domains from the project's technology requirements and scope of work

Tender document text:
{text}"""

TENDER_VERIFICATION_PROMPT = """Verify this extracted tender data against the source text. List any issues:

Extracted:
- Project: {project_name}
- Client: {client}
- Roles ({role_count}): {roles_snippet}
- Technologies: {technologies}

Source text (first 8000 chars):
{raw_snippet}

Return JSON: {{"issues": ["issue1", "issue2"], "is_valid": true/false}}
If no issues, return {{"issues": [], "is_valid": true}}"""

TENDER_FIX_ISSUES_PROMPT = """The following extraction had issues that need fixing:

Issues found:
{issues_json}

Current extracted data:
{data_json}

Source document (first 15000 chars):
{raw_snippet}

Fix ONLY the identified issues. Ensure you maintain the exact JSON schema. Return the complete corrected JSON data."""

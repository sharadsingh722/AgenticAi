"""Prompts for matching agent."""

MATCHING_CRITERIA_PROMPT = """Determine the most important evaluation criteria for selecting a candidate for this role.

Project: {project_name}
Client: {client}
Technologies: {technologies}

Role: {role_title}
Required Experience: {min_experience} years
Required Skills: {required_skills}
Required Certifications: {required_certifications}
Required Domain: {required_domain}
Preferred Components: {preferred_components}
Min Project Value: {min_project_value_cr} Cr
Client Type Preference: {client_type_preference}

Return 4-6 criteria with weights summing to 1.0. Consider what matters most for THIS specific role in THIS project context, strongly taking into account domain, project scale, and components."""

MATCHING_EVALUATION_PROMPT = """Evaluate this candidate for the role using evidence from their resume.

ROLE: {role_title}
Project Requirements:
- Min Experience: {min_experience} years
- Min Project Value: {min_project_value_cr} Cr
- Client Priority: {client_type_preference}
- Required Skills: {required_skills}
- Required Domains: {required_domain}
- Preferred Components: {preferred_components}
- Required Certifications: {required_certifications}

SCORING CRITERIA:
{criteria_text}

CANDIDATE: {candidate_name}
Summary Profile:
- Total Experience: {years_experience} years
- Domains: {domains}
- Skills: {skills}
- Certifications: {certifications}
- Education: {education}
- Derived Profile: {derived_profile}

Experience History:
{experience_history}

Score this candidate 0-100 overall and per criterion. 
Ensure your evaluation is strictly evidence-based. Do not hallucinate skills or experience.
Be specific about where their experience aligns with the project scale (value/length) and components.
Provide 3 specific strengths and 2-3 specific concerns. Ensure the explanation gives a clear rationale for the score."""

export interface ExperienceItem {
  company: string;
  role: string;
  duration: string;
  description: string;
}

export interface Resume {
  id: number;
  name: string;
  email: string | null;
  phone: string | null;
  skills: string[];
  total_years_experience: number;
  domain_expertise: string[];
  file_name: string;
  photo_url: string | null;
  parse_status: string;
  created_at: string;
}

export interface ResumeDetail extends Resume {
  experience: ExperienceItem[];
  education: string[];
  certifications: string[];
  raw_text: string;
}

export interface RequiredRole {
  role_title: string;
  min_experience: number;
  required_skills: string[];
  required_certifications: string[];
  required_domain: string[];
}

export interface Tender {
  id: number;
  project_name: string;
  client: string | null;
  document_reference: string | null;
  document_date: string | null;
  roles_count: number;
  key_technologies: string[];
  file_name: string;
  parse_status: string;
  created_at: string;
}

export interface TenderDetail {
  id: number;
  project_name: string;
  client: string | null;
  document_reference: string | null;
  document_date: string | null;
  required_roles: RequiredRole[];
  eligibility_criteria: string[];
  project_duration: string | null;
  key_technologies: string[];
  file_name: string;
  parse_status: string;
  raw_text: string;
  created_at: string;
}

export interface ScoreBreakdown {
  experience: number;
  skills: number;
  domain: number;
  certifications: number;
  education: number;
}

export interface MatchResultItem {
  resume_id: number;
  candidate_name: string;
  role_title: string;
  final_score: number;
  semantic_score: number;
  structured_score: number;
  score_breakdown: ScoreBreakdown;
  matched_skills: string[];
  missing_skills: string[];
  experience_years: number;
  designation: string | null;
  photo_url: string | null;
  llm_score: number | null;
  llm_explanation: string | null;
  strengths: string[];
  concerns: string[];
}

export interface RoleRequirements {
  min_experience: number;
  required_skills: string[];
  required_certifications: string[];
  required_domain: string[];
}

export interface MatchResponse {
  tender_id: number;
  project_name: string;
  role_title: string;
  role_requirements: RoleRequirements | null;
  results: MatchResultItem[];
}

export interface BatchUploadResult {
  uploaded: number;
  errors: { file: string; error: string }[];
  resumes: Resume[];
}

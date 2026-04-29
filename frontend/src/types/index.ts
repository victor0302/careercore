/**
 * TypeScript interfaces matching the backend Pydantic schemas.
 * Keep in sync with backend/app/schemas/.
 */

// ── Auth ─────────────────────────────────────────────────────────────────────

export type UserTier = "free" | "standard";

export interface User {
  id: string;
  email: string;
  is_active: boolean;
  tier: UserTier;
}

export interface AccessTokenResponse {
  access_token: string;
  token_type: string;
}

// ── Profile ───────────────────────────────────────────────────────────────────

export interface MasterProfile {
  id: string;
  user_id: string;
  display_name: string | null;
  current_title: string | null;
  target_domain: string | null;
  summary_notes: string | null;
  completeness_pct: number;
}

export interface ProfileUpdate {
  display_name?: string | null;
  current_title?: string | null;
  target_domain?: string | null;
  summary_notes?: string | null;
}

export interface WorkExperience {
  id: string;
  profile_id: string;
  source_file_id: string | null;
  employer: string;
  role_title: string;
  start_date: string; // ISO date string
  end_date: string | null;
  is_current: boolean;
  description_raw: string | null;
  bullets: string[] | null;
  skill_tags: string[] | null;
  tool_tags: string[] | null;
  domain_tags: string[] | null;
}

export interface Project {
  id: string;
  profile_id: string;
  name: string;
  description_raw: string | null;
  url: string | null;
  bullets: string[] | null;
  skill_tags: string[] | null;
  tool_tags: string[] | null;
  domain_tags: string[] | null;
}

export interface Skill {
  id: string;
  profile_id: string;
  name: string;
  category: string | null;
  proficiency_level: string | null;
  years_of_experience: number | null;
}

export interface Certification {
  id: string;
  profile_id: string;
  name: string;
  issuer: string | null;
  issued_date: string | null;
  expiry_date: string | null;
  credential_id: string | null;
  credential_url: string | null;
}

// ── Jobs ─────────────────────────────────────────────────────────────────────

export interface JobAnalysisSummaryRead {
  id: string;
  fit_score: number;
  analyzed_at: string;
}

export interface MatchedRequirementRead {
  id: string;
  requirement_id: string;
  match_type: string;
  source_entity_type: string;
  source_entity_id: string;
  confidence: number;
}

export interface MissingRequirementRead {
  id: string;
  requirement_id: string;
  suggested_action: string | null;
}

export interface JobAnalysisDetailRead extends JobAnalysisSummaryRead {
  score_breakdown: Record<string, unknown>;
  evidence_map: Record<string, unknown>;
  matched_requirements: MatchedRequirementRead[];
  missing_requirements: MissingRequirementRead[];
}

export interface JobListRead {
  id: string;
  user_id: string;
  title: string;
  company: string | null;
  raw_text: string;
  parsed_at: string | null;
  latest_analysis: JobAnalysisSummaryRead | null;
}

export interface JobDetailRead {
  id: string;
  user_id: string;
  title: string;
  company: string | null;
  raw_text: string;
  parsed_at: string | null;
  latest_analysis: JobAnalysisDetailRead | null;
}

/** @deprecated Use JobListRead or JobDetailRead */
export interface JobDescription {
  id: string;
  user_id: string;
  title: string;
  company: string | null;
  raw_text: string;
  parsed_at: string | null;
}

/** @deprecated Use JobAnalysisDetailRead */
export interface JobAnalysis {
  id: string;
  job_id: string;
  user_id: string;
  fit_score: number;
  score_breakdown: Record<string, unknown>;
  analyzed_at: string;
}

// ── Resumes ───────────────────────────────────────────────────────────────────

export interface Resume {
  id: string;
  user_id: string;
  job_id: string | null;
}

export interface ResumeRead {
  id: string;
  user_id: string;
  job_id: string | null;
}

export interface ResumeVersion {
  id: string;
  resume_id: string;
  fit_score_at_gen: number | null;
}

export interface ResumeBullet {
  id: string;
  resume_id: string;
  text: string;
  is_ai_generated: boolean;
  is_approved: boolean;
  confidence: number | null;
}

export interface ResumeBulletRead {
  id: string;
  resume_id: string;
  text: string;
  is_ai_generated: boolean;
  is_approved: boolean;
  confidence: number | null;
}

export interface BulletsGenerateRequest {
  profile_entity_type: "work_experience" | "project";
  profile_entity_id: string;
  requirement_ids: string[];
}

export interface EvidenceLinkRead {
  source_entity_type: string;
  source_entity_id: string;
  display_name: string;
}

export interface ResumeBulletWithEvidence {
  id: string;
  text: string;
  confidence: number | null;
  evidence: EvidenceLinkRead[];
}

export interface ResumeVersionListItem {
  id: string;
  resume_id: string;
  fit_score_at_gen: number | null;
  created_at: string;
  job_title: string | null;
  job_company: string | null;
}

export interface ResumeVersionDetailRead {
  id: string;
  resume_id: string;
  fit_score_at_gen: number | null;
  created_at: string;
  job_title: string | null;
  job_company: string | null;
  bullets: ResumeBulletWithEvidence[];
}

// ── API responses ─────────────────────────────────────────────────────────────

export interface ApiError {
  detail: string;
}

// ── Files ─────────────────────────────────────────────────────────────────────

export interface FileUploadResponse {
  id: string;
  status: string; // "pending" | "processing" | "ready" | "error"
  filename: string;
}

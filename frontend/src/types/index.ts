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

export interface TokenPair {
  access_token: string;
  refresh_token: string;
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

export interface WorkExperience {
  id: string;
  profile_id: string;
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

export interface JobDescription {
  id: string;
  user_id: string;
  title: string;
  company: string | null;
  raw_text: string;
  parsed_at: string | null;
}

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

// ── API responses ─────────────────────────────────────────────────────────────

export interface ApiError {
  detail: string;
}

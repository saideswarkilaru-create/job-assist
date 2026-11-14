import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { firstValueFrom } from 'rxjs';

export interface Meta {
  posted_within: { value: string; label: string }[];
  job_types: string[];
  experience_levels: string[];
  work_modes: string[];
  job_statuses: string[];
  run_kinds: Record<string, string>;
  implemented_sites: string[];
  claude_cli: boolean;
  analysis_engine: 'builtin' | 'claude';
}

export interface Profile {
  id?: number;
  name: string;
  enabled: boolean;
  keywords: string[];
  must_include: string[];
  must_include_mode: 'all' | 'any';
  exclude: string[];
  locations: string[];
  work_modes: string[];
  posted_within: string;
  job_types: string[];
  experience_levels: string[];
  sites: string[];
  resume_id: number | null;
  min_score: number;
  max_jobs: number;
  max_years: number;
  jobs_matched?: number;
  last_run_at?: string | null;
}

export interface Resume {
  id: number;
  name: string;
  file_name: string;
  original_name: string;
  is_default: boolean;
  uploaded_at: string;
  text_chars: number;
  used_by: number;
  text?: string;
  top_skills?: string[];
  years_estimate?: number | null;
  source_ext?: string;
  converted_by?: string;
  design?: string;
  parent_id?: number | null;
}

export interface SuggestItem {
  value: string;
  reason: string;
  selected: boolean;
  source: string;
}

export interface Suggestions {
  resume: { id: number; name: string };
  engine: string;
  skills: { name: string; category: string; count: number }[];
  experience: { years: number | null; includes_internships: boolean; settings_years: number | null;
                ranges: { from: string; to: string; line: string }[] };
  roles: { name: string; confidence: number; matched: string[] }[];
  suggestions: { keywords: SuggestItem[]; exclude: SuggestItem[]; must_include: SuggestItem[] };
  profile_defaults: { name: string; max_years: number; experience_levels: string[] };
}

export interface Site {
  id: number;
  key: string;
  name: string;
  kind: 'builtin' | 'custom';
  search_url: string | null;
  enabled: boolean;
  notes: string;
}

export interface Company {
  id: number;
  name: string;
  careers_url: string;
  enabled: boolean;
  adapter: string | null;
  notes: string;
  last_status: string;
  last_checked_at: string | null;
}

export interface Login {
  login_key: string;
  name: string;
  url: string;
  mode: 'manual' | 'saved';
  username: string;
  password_saved: boolean;
}

export interface Analysis {
  score: number;
  required_skills: string[];
  nice_to_have: string[];
  matched: string[];
  missing: string[];
  emphasize: string[];
  years_required: string | null;
  seniority: string | null;
  work_authorization: string | null;
  summary: string;
  resume_name?: string;
  engine?: string;
  auth_blockers?: string[];
  employer_type?: string;
}

export interface Job {
  id: number;
  url: string;
  site: string;
  title: string;
  company: string;
  location: string;
  work_mode: string;
  job_type: string;
  posted_at: string;
  posted_text: string;
  status: string;
  status_note: string;
  match_score: number | null;
  matched_keywords: string[];
  missing_keywords: string[];
  analyzed_at: string | null;
  first_seen_at: string;
  profiles: string | null;
  filtered_reason?: string | null;
  years_required: number | null;
  auth_flags: string[];
  employer_type: string;
  applicants: string;
  apply_type: string;
  also_on?: string | null;
  description?: string;
  analysis?: Analysis | null;
  tailored_docx?: string | null;
  tailored_pdf?: string | null;
  tailored_at?: string | null;
  tailor_report?: TailorReport | null;
  cover_note?: string | null;
  cover_note_path?: string | null;
  hits?: { profile_name: string; keyword: string; location: string; matched: number; reason: string }[];
}

export interface TailorReport {
  base_resume?: string;
  matched_used: string[];
  bullets_moved_up: string[];
  bullet_blocks: number;
  bullets_reordered: number;
  skill_lines_reordered: number;
  key_skills_line: string | null;
  reword: { accepted: number; rejected: number; note?: string; rejected_examples?: string[] } | null;
  gaps: string[];
  guard: string;
  fallback: boolean;
  pdf_method?: string | null;
  pdf_error?: string;
}

export interface Run {
  id: number;
  kind: string;
  profile_id: number | null;
  profile_name: string | null;
  job_id: number | null;
  job_title: string | null;
  trigger: string;
  status: 'queued' | 'running' | 'waiting_user' | 'done' | 'failed' | 'cancelled';
  message: string;
  jobs_seen: number;
  jobs_new: number;
  jobs_matched: number;
  started_at: string;
  finished_at: string | null;
  payload?: {
    job_id: number; title: string; company: string; resume: string | null; final_button: string | null;
    note: string; url: string; steps: number;
    filled: { label: string; value: string; source: string }[];
    needs_you: { label: string; why: string }[];
    kept: { label: string; value: string }[];
  } | null;
}

export interface SettingSpec {
  key: string;
  label: string;
  type: 'number' | 'bool' | 'select' | 'time' | 'text' | 'textarea';
  default: unknown;
  min?: number;
  max?: number;
  options?: string[];
  group: string;
  phase?: number;
}

@Injectable({ providedIn: 'root' })
export class Api {
  private http = inject(HttpClient);
  private snack = inject(MatSnackBar);

  /** Active runs, polled by the shell so every page can react to them. */
  readonly activeRuns = signal<Run[]>([]);
  readonly meta = signal<Meta | null>(null);

  get<T>(url: string, params?: Record<string, string | number | boolean | null | undefined>): Promise<T> {
    const clean: Record<string, string> = {};
    for (const [k, v] of Object.entries(params ?? {})) {
      if (v !== null && v !== undefined && v !== '') clean[k] = String(v);
    }
    return this.wrap(this.http.get<T>('/api' + url, { params: clean }));
  }
  post<T>(url: string, body: unknown = {}): Promise<T> {
    return this.wrap(this.http.post<T>('/api' + url, body));
  }
  put<T>(url: string, body: unknown): Promise<T> {
    return this.wrap(this.http.put<T>('/api' + url, body));
  }
  patch<T>(url: string, body: unknown): Promise<T> {
    return this.wrap(this.http.patch<T>('/api' + url, body));
  }
  delete<T>(url: string): Promise<T> {
    return this.wrap(this.http.delete<T>('/api' + url));
  }
  text(url: string): Promise<string> {
    return this.wrap(this.http.get('/api' + url, { responseType: 'text' }));
  }

  async loadMeta(): Promise<Meta> {
    const m = this.meta() ?? (await this.get<Meta>('/meta'));
    this.meta.set(m);
    return m;
  }

  async refreshRuns(): Promise<void> {
    try {
      this.activeRuns.set(await firstValueFrom(this.http.get<Run[]>('/api/runs/active')));
    } catch {
      /* backend restarting; keep last state */
    }
  }

  toast(message: string, isError = false): void {
    this.snack.open(message, 'OK', { duration: isError ? 8000 : 3500, panelClass: isError ? 'snack-error' : '' });
  }

  private async wrap<T>(obs: import('rxjs').Observable<T>): Promise<T> {
    try {
      return await firstValueFrom(obs);
    } catch (e) {
      const err = e as HttpErrorResponse;
      const msg = (err.error && (err.error.detail || err.error)) || err.message || 'Request failed';
      this.toast(typeof msg === 'string' ? msg : JSON.stringify(msg), true);
      throw e;
    }
  }
}

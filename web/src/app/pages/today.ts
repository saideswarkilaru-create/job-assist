import { Component, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { Api, Job, Profile, Site } from '../api';

@Component({
  selector: 'app-today',
  imports: [
    FormsModule, DatePipe, MatButtonModule, MatFormFieldModule, MatIconModule, MatInputModule,
    MatSelectModule, MatSlideToggleModule, MatTooltipModule, RouterLink,
  ],
  template: `
    <div class="page-head">
      <div class="grow">
        <h1>Today</h1>
        <p class="sub">Jobs your profiles found, best match first. Click a title to see the skills the job asks for and how your resume compares.</p>
      </div>
      <button mat-stroked-button (click)="analyzeNew()" [disabled]="busy()"
        matTooltip="Score every new job description against your resume">
        <mat-icon>psychology</mat-icon> Analyze new jobs
      </button>
    </div>

    <div class="panel row filters">
      <mat-form-field subscriptSizing="dynamic">
        <mat-label>Profile</mat-label>
        <mat-select [(ngModel)]="f.profile_id" (selectionChange)="load()">
          <mat-option [value]="null">All profiles</mat-option>
          @for (p of profiles(); track p.id) { <mat-option [value]="p.id">{{ p.name }}</mat-option> }
        </mat-select>
      </mat-form-field>
      <mat-form-field subscriptSizing="dynamic">
        <mat-label>Site</mat-label>
        <mat-select [(ngModel)]="f.site" (selectionChange)="load()">
          <mat-option [value]="null">All sites</mat-option>
          @for (s of sites(); track s.key) { <mat-option [value]="s.key">{{ s.name }}</mat-option> }
        </mat-select>
      </mat-form-field>
      <mat-form-field subscriptSizing="dynamic">
        <mat-label>Status</mat-label>
        <mat-select [(ngModel)]="f.status" (selectionChange)="load()">
          <mat-option [value]="null">Any status</mat-option>
          @for (s of api.meta()?.job_statuses ?? []; track s) { <mat-option [value]="s">{{ s }}</mat-option> }
        </mat-select>
      </mat-form-field>
      <mat-form-field subscriptSizing="dynamic" class="narrow">
        <mat-label>Min score</mat-label>
        <input matInput type="number" min="0" max="100" [(ngModel)]="f.min_score" (change)="load()" />
      </mat-form-field>
      <mat-form-field subscriptSizing="dynamic">
        <mat-label>Search title / company</mat-label>
        <input matInput [(ngModel)]="f.q" (keyup.enter)="load()" />
      </mat-form-field>
      <mat-slide-toggle [(ngModel)]="f.include_filtered" (change)="load()">Show filtered-out</mat-slide-toggle>
    </div>

    @if (jobs().length === 0) {
      <div class="panel empty">
        No jobs yet. Create a profile, then press <b>Run this profile now</b> or <b>Run all now</b>.
      </div>
    } @else {
      <div class="table-wrap">
        <table class="data">
          <thead>
            <tr><th>Score</th><th>Job</th><th>Location</th><th>Site</th><th>Posted</th><th>Status</th><th>Profiles</th><th></th></tr>
          </thead>
          <tbody>
            @for (j of jobs(); track j.id) {
              <tr [class.open]="openId() === j.id">
                <td><span class="score" [class]="scoreClass(j.match_score)">{{ j.match_score ?? '–' }}</span></td>
                <td class="job-cell">
                  <a href="" (click)="$event.preventDefault(); toggle(j)" class="title">{{ j.title || '(no title)' }}</a>
                  <div class="muted small">{{ j.company }} @if (j.job_type) { · {{ j.job_type }} } @if (j.work_mode) { · {{ j.work_mode }} }</div>
                  <div class="badges">
                    @for (b of badges(j); track b.label) {
                      <span class="tag" [class]="'tag ' + b.tone" [matTooltip]="b.tip">{{ b.label }}</span>
                    }
                  </div>
                  @if (j.filtered_reason && !j.profiles) { <div class="tag bad">filtered: {{ j.filtered_reason }}</div> }
                </td>
                <td class="small">{{ j.location }}</td>
                <td class="small">{{ j.site }}</td>
                <td class="small nowrap">{{ j.posted_at ? (j.posted_at | date: 'MMM d, h:mm a') : j.posted_text }}</td>
                <td><span class="tag" [class]="statusTone(j.status)">{{ j.status }}</span>
                  @if (j.status_note) { <div class="muted small">{{ j.status_note }}</div> }
                </td>
                <td class="small">{{ j.profiles }}</td>
                <td class="act-cell">
                  <div class="actions nowrap">
                    <button mat-flat-button (click)="tailorApply(j)" [disabled]="busy()"
                      matTooltip="One click: read JD → tailor resume → fill the application and stop before Submit">
                      <mat-icon>bolt</mat-icon> Tailor &amp; Apply
                    </button>
                    @if (j.status !== 'Applied') {
                      <button mat-icon-button (click)="apply(j)" [disabled]="busy()" matTooltip="Fill the application for me (stops before Submit)"><mat-icon>send</mat-icon></button>
                    }
                    @if (j.tailored_docx) {
                      <a mat-icon-button [href]="'/api/jobs/' + j.id + '/file/docx'" matTooltip="Download tailored resume (Word)"><mat-icon>description</mat-icon></a>
                    } @else {
                      <button mat-icon-button (click)="tailor(j)" [disabled]="busy()" matTooltip="Tailor my resume for this job"><mat-icon>edit_document</mat-icon></button>
                    }
                    <a mat-icon-button [href]="j.url" target="_blank" rel="noopener" matTooltip="Open JD on the site"><mat-icon>open_in_new</mat-icon></a>
                    <button mat-icon-button (click)="setStatus(j, 'Skipped')" matTooltip="Skip"><mat-icon>block</mat-icon></button>
                  </div>
                </td>
              </tr>
              @if (openId() === j.id) {
                <tr class="open">
                  <td colspan="8">
                    @if (detail(); as d) {
                      <div class="detail">
                        <div>
                          @if (d.analysis; as a) {
                            <h2>Fit: {{ a.score }}/100 <span class="muted small">vs resume "{{ a.resume_name }}"
                              · {{ a.engine === 'claude' ? 'Claude' : 'built-in matcher' }}</span></h2>
                            <p>{{ a.summary }}</p>
                            <div class="kv">
                              @if (a.years_required) { <span><b>Experience asked:</b> {{ a.years_required }}</span> }
                              @if (a.seniority) { <span><b>Seniority:</b> {{ a.seniority }}</span> }
                              @if (a.work_authorization) { <span><b>Work authorization:</b> {{ a.work_authorization }}</span> }
                            </div>
                            <h3>Skills you match ({{ a.matched.length }})</h3>
                            <div>@for (s of a.matched; track s) { <span class="tag good">{{ s }}</span> }</div>
                            <h3>Gaps: in the JD, not in your resume ({{ a.missing.length }})</h3>
                            <p class="muted small">These are for you to review. They are never added to your resume.</p>
                            <div>@for (s of a.missing; track s) { <span class="tag warn">{{ s }}</span> }</div>
                            <h3>Emphasize in the tailored resume</h3>
                            <div>@for (s of a.emphasize; track s) { <span class="tag info">{{ s }}</span> }</div>
                            @if (a.nice_to_have.length) {
                              <h3>Nice to have</h3>
                              <div>@for (s of a.nice_to_have; track s) { <span class="tag">{{ s }}</span> }</div>
                            }
                          } @else {
                            <h2>Not analyzed yet</h2>
                            <p class="muted">The app will read the description, list the skills it asks for, and compare them with your resume.</p>
                          }
                          <div class="actions" style="margin-top:14px">
                            <button mat-stroked-button (click)="analyze(j)" [disabled]="busy()">
                              <mat-icon>psychology</mat-icon> {{ d.analysis ? 'Re-analyze' : 'Analyze now' }}
                            </button>
                            <button mat-stroked-button (click)="setStatus(j, 'New')">Mark New</button>
                            <button mat-stroked-button (click)="setStatus(j, 'Manual')">Mark Manual</button>
                          </div>
                          <div class="tailored">
                            <h2>Tailored resume</h2>
                            @if (d.tailored_docx && d.tailor_report; as r) {
                              <div class="actions">
                                <a mat-flat-button [href]="'/api/jobs/' + d.id + '/file/docx'"><mat-icon>download</mat-icon> Word</a>
                                @if (d.tailored_pdf) { <a mat-stroked-button [href]="'/api/jobs/' + d.id + '/file/pdf'"><mat-icon>picture_as_pdf</mat-icon> PDF</a> }
                                <button mat-button (click)="tailor(j)" [disabled]="busy()">Tailor again</button>
                              </div>
                              <div class="row rename">
                                <mat-form-field subscriptSizing="dynamic" class="fname">
                                  <mat-label>File name the employer will see</mat-label>
                                  <input matInput [(ngModel)]="renameTo" />
                                  <span matTextSuffix>.docx / .pdf</span>
                                </mat-form-field>
                                <button mat-stroked-button (click)="rename(d, renameTo)" [disabled]="!renameTo.trim() || renameTo === stem(d.tailored_docx)">Rename</button>
                              </div>
                              <p class="muted small">From "{{ r.base_resume }}"
                                @if (r.pdf_method) { · PDF via {{ pdfLabel(r.pdf_method) }} }
                                @if (r.pdf_error) { · <span class="tag warn">PDF not made</span> }</p>
                              @if (r.fallback) {
                                <div class="tag bad">Honesty check failed ({{ r.guard }}). Your base resume was used unchanged.</div>
                              } @else {
                                <div class="tag good">Honesty check passed: nothing added that isn't in your resume</div>
                              }
                              <ul class="changes">
                                @if (r.bullets_reordered) { <li>Moved {{ r.bullets_reordered }} bullet(s) so the most relevant come first in each job</li> }
                                @for (b of r.bullets_moved_up; track b) { <li class="muted small">Now first: "{{ b }}…"</li> }
                                @if (r.skill_lines_reordered) { <li>Put this job's skills first in {{ r.skill_lines_reordered }} skills line(s)</li> }
                                @if (r.key_skills_line) { <li>Added under your summary: <i>{{ r.key_skills_line }}</i></li> }
                                @if (r.reword) { <li>Claude rewording: {{ r.reword.accepted }} accepted, {{ r.reword.rejected }} rejected by the check</li> }
                                @if (!r.bullets_reordered && !r.skill_lines_reordered && !r.key_skills_line) { <li>Your resume already fits this job's order; no changes needed</li> }
                              </ul>
                              @if (r.gaps.length) {
                                <p class="small"><b>Gaps to think about</b> (not added): {{ r.gaps.slice(0, 8).join(', ') }}</p>
                              }
                              @if (d.cover_note) {
                                <h3>Cover note</h3>
                                <textarea class="note" readonly rows="9">{{ d.cover_note }}</textarea>
                                <div class="actions">
                                  <button mat-stroked-button (click)="copy(d.cover_note)"><mat-icon>content_copy</mat-icon> Copy</button>
                                  <a mat-button [href]="'/api/jobs/' + d.id + '/file/cover'">Download .txt</a>
                                </div>
                              }
                            } @else {
                              <p class="muted small">Makes a copy of your resume for this job: most relevant bullets first, this job's skills first and
                                bold. Nothing is invented.</p>
                              <button mat-flat-button (click)="tailor(j)" [disabled]="busy()"><mat-icon>edit_document</mat-icon> Tailor resume</button>
                            }
                          </div>
                          <div class="applied">
                            @if (d.status === 'Applied') {
                              <span class="tag good"><mat-icon class="ico">task_alt</mat-icon> Applied</span>
                              <a mat-button routerLink="/applications">Track it in Applications</a>
                            } @else {
                              <h3>Apply</h3>
                              <div class="row">
                                <button mat-flat-button (click)="apply(d)" [disabled]="busy()"><mat-icon>send</mat-icon> Fill the application for me</button>
                                <span class="muted small">Opens the application, fills it from My details, attaches
                                  {{ d.tailored_pdf || d.tailored_docx ? 'your tailored resume' : 'your resume' }}, and stops before Submit.</span>
                              </div>
                              <h3>Applied another way?</h3>
                              <div class="row">
                                <input type="date" class="date" [(ngModel)]="applyForm.applied_on" />
                                <mat-select class="chan" [(ngModel)]="applyForm.channel" placeholder="How did you apply?">
                                  <mat-option value="easy_apply">Easy Apply (on the site)</mat-option>
                                  <mat-option value="company_site">Company website</mat-option>
                                  <mat-option value="email">Email to recruiter</mat-option>
                                  <mat-option value="referral">Referral</mat-option>
                                  <mat-option value="other">Other</mat-option>
                                </mat-select>
                                <button mat-flat-button (click)="markApplied(d)"><mat-icon>task_alt</mat-icon> Mark as applied</button>
                              </div>
                              <p class="muted small">Logs the date, the resume you sent ({{ d.tailored_pdf || d.tailored_docx ? 'your tailored one' : 'your base resume' }}) and sets a follow-up reminder.</p>
                            }
                          </div>
                          @if (d.hits?.length) {
                            <h3>Why it showed up</h3>
                            @for (h of d.hits; track h.profile_name) {
                              <div class="small">
                                <b>{{ h.profile_name }}</b>: keyword "{{ h.keyword }}"@if (h.location) { in {{ h.location }} } ·
                                <span [class]="h.matched ? 'tag good' : 'tag bad'">{{ h.reason }}</span>
                              </div>
                            }
                          }
                        </div>
                        <div>
                          <h2>Job description</h2>
                          <div class="jd">{{ d.description || 'No description saved. Open the job on the site.' }}</div>
                        </div>
                      </div>
                    } @else {
                      <span class="muted">Loading…</span>
                    }
                  </td>
                </tr>
              }
            }
          </tbody>
        </table>
      </div>
    }
  `,
  styles: `
    .filters mat-form-field { width: 180px; }
    .filters .narrow { width: 110px; }
    .title { font-weight: 600; text-decoration: none; }
    .badges { margin-top: 4px; }
    .applied { margin-top: 14px; }
    .applied .date { font: inherit; padding: 6px; border: 1px solid var(--line); border-radius: 6px; }
    .applied .chan { width: 210px; }
    .ico { font-size: 16px; width: 16px; height: 16px; vertical-align: -3px; }
    .rename { margin: 8px 0 2px; flex-wrap: nowrap; } .fname { flex: 1; min-width: 0; }
    .tailored { margin-top: 18px; padding: 14px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); }
    .changes { margin: 8px 0; padding-left: 18px; font-size: 13px; }
    .note { width: 100%; box-sizing: border-box; font: inherit; font-size: 13px; padding: 8px; border: 1px solid var(--line); border-radius: 6px; }
    .job-cell { min-width: 260px; }
    .nowrap { white-space: nowrap; }
    .nowrap.actions { flex-wrap: nowrap; }
    .act-cell { width: 1%; }
    .detail { display: grid; grid-template-columns: minmax(300px, 1fr) minmax(300px, 1.2fr); gap: 24px; padding: 6px 4px; }
    h3 { font-size: 13px; margin: 14px 0 6px; }
    .kv { display: flex; gap: 16px; flex-wrap: wrap; font-size: 13px; }
  `,
})
export class TodayPage {
  protected api = inject(Api);
  protected jobs = signal<Job[]>([]);
  protected profiles = signal<Profile[]>([]);
  protected sites = signal<Site[]>([]);
  protected openId = signal<number | null>(null);
  protected detail = signal<Job | null>(null);
  protected busy = computed(() => this.api.activeRuns().length > 0);
  protected f = { profile_id: null as number | null, site: null as string | null, status: null as string | null,
    min_score: null as number | null, q: '', include_filtered: false };

  constructor() {
    this.api.get<Profile[]>('/profiles').then((p) => this.profiles.set(p));
    this.api.get<Site[]>('/sites').then((s) => this.sites.set(s));
    this.load();
    // When a run finishes, refresh the list and the open job.
    let wasBusy = false;
    effect(() => {
      const b = this.busy();
      if (wasBusy && !b) {
        this.load();
        const id = this.openId();
        if (id) this.loadDetail(id);
      }
      wasBusy = b;
    });
  }

  async load() {
    this.jobs.set(await this.api.get<Job[]>('/jobs', this.f));
  }

  async toggle(j: Job) {
    if (this.openId() === j.id) { this.openId.set(null); return; }
    this.openId.set(j.id);
    this.detail.set(null);
    this.loadDetail(j.id);
  }

  protected renameTo = '';

  private async loadDetail(id: number) {
    const d = await this.api.get<Job>(`/jobs/${id}`);
    this.renameTo = this.stem(d.tailored_docx) ?? '';
    this.detail.set(d);
  }

  async analyze(j: Job) {
    await this.api.post('/jobs/analyze', { job_ids: [j.id] });
    this.api.toast('Claude is reading the job description…');
    this.api.refreshRuns();
  }

  async analyzeNew() {
    await this.api.post('/jobs/analyze', {});
    this.api.toast('Analyzing all new jobs that have not been scored yet…');
    this.api.refreshRuns();
  }

  protected applyForm = { applied_on: new Date().toISOString().slice(0, 10), channel: '' };

  async markApplied(d: Job) {
    await this.api.post(`/jobs/${d.id}/applied`, { applied_on: this.applyForm.applied_on, channel: this.applyForm.channel });
    this.api.toast(`Logged: applied to ${d.company}. Follow-up reminder set.`);
    this.load();
    this.loadDetail(d.id);
  }

  stem(p: string | null | undefined) {
    return (this.fileName(p) ?? '').replace(/\.(docx|pdf)$/i, '');
  }

  async rename(d: Job, name: string) {
    await this.api.post(`/jobs/${d.id}/rename-tailored`, { name });
    this.api.toast('Renamed');
    this.loadDetail(d.id);
  }

  async tailor(j: Job) {
    await this.api.post(`/jobs/${j.id}/tailor`);
    this.api.toast('Tailoring your resume for this job…');
    this.api.refreshRuns();
    this.openId.set(j.id);
    this.loadDetail(j.id);
  }

  fileName(p: string | null | undefined) {
    return (p ?? '').split(/[\\/]/).pop();
  }

  pdfLabel(m: string) {
    return ({ word: 'Microsoft Word', libreoffice: 'LibreOffice', browser: 'built-in converter' } as Record<string, string>)[m] ?? m;
  }

  async copy(text: string) {
    await navigator.clipboard.writeText(text);
    this.api.toast('Cover note copied');
  }

  async apply(j: Job) {
    await this.api.post(`/jobs/${j.id}/apply`);
    this.api.toast('Opening the application in the browser window. Nothing is sent until you approve.');
    this.api.refreshRuns();
  }

  async tailorApply(j: Job) {
    await this.api.post(`/jobs/${j.id}/tailor-apply`);
    this.api.toast('Tailor & Apply started: score, tailor, then fill the form. It stops before Submit for your review.');
    this.api.refreshRuns();
    this.openId.set(j.id);
  }

  async setStatus(j: Job, status: string) {
    await this.api.patch(`/jobs/${j.id}`, { status });
    this.load();
  }

  private static FLAG: Record<string, { label: string; tone: string; tip: string }> = {
    no_sponsorship: { label: 'No sponsorship', tone: 'bad', tip: 'The description says the employer will not sponsor a visa' },
    no_opt: { label: 'No OPT', tone: 'bad', tip: 'The description rules out OPT/CPT candidates' },
    usc_only: { label: 'US citizens only', tone: 'bad', tip: 'Requires US citizenship' },
    usc_gc_only: { label: 'USC / GC only', tone: 'bad', tip: 'Only US citizens or green card holders' },
    clearance: { label: 'Clearance', tone: 'bad', tip: 'Needs a security clearance (usually US citizens only)' },
    sponsor_friendly: { label: 'Sponsor / OPT OK', tone: 'good', tip: 'Mentions sponsorship, H-1B transfer or OPT/CPT welcome' },
    w2_only: { label: 'W2 only', tone: '', tip: 'No corp-to-corp; you would be on the employer’s payroll' },
  };

  badges(j: Job) {
    const out = (j.auth_flags ?? []).map((f) => TodayPage.FLAG[f]).filter(Boolean);
    if (j.years_required) out.push({ label: `${j.years_required}+ yrs`, tone: j.years_required > 3 ? 'warn' : '', tip: 'Minimum years of experience the job asks for' });
    if (j.employer_type === 'staffing') out.push({ label: 'Staffing / vendor', tone: 'warn', tip: 'Posted by a staffing agency or for an end client' });
    if (j.apply_type === 'easy_apply') out.push({ label: 'Easy Apply', tone: 'info', tip: 'Apply inside the job site' });
    if (j.applicants) out.push({ label: j.applicants, tone: '', tip: 'How many people already applied (earlier is better)' });
    if (j.also_on) out.push({ label: 'Also on ' + j.also_on, tone: 'info', tip: 'Same job found on other sites; shown once' });
    return out;
  }

  scoreClass(s: number | null) {
    if (s === null || s === undefined) return 'score none';
    return 'score ' + (s >= 75 ? 'hi' : s >= 55 ? 'mid' : 'lo');
  }

  statusTone(s: string) {
    return 'tag ' + ({ New: 'info', Tailored: 'good', 'Ready to review': 'good', Applied: 'good', Skipped: '', Manual: 'warn', Failed: 'bad' } as Record<string, string>)[s];
  }
}

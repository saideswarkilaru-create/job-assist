import { Component, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDialog } from '@angular/material/dialog';
import { Router } from '@angular/router';
import { Api, Profile, Resume } from '../api';
import { SuggestDialog, SuggestResult, mergeList } from '../shared/suggest-dialog';
import { openResumeCheck, openResumeDesigns } from '../shared/resume-dialogs';

@Component({
  selector: 'app-resumes',
  imports: [DatePipe, DecimalPipe, FormsModule, MatButtonModule, MatFormFieldModule, MatIconModule, MatInputModule, MatTooltipModule],
  template: `
    <div class="page-head">
      <div class="grow">
        <h1>Resumes</h1>
        <p class="sub">Your base resumes (Word or PDF). Each profile picks one; tailored copies are made from it and never invent anything.
          Use <b>Check</b> for recruiter tips and <b>Designs</b> for a cleaner layout of the same content.</p>
      </div>
    </div>

    <div class="panel">
      <h2>Upload a base resume</h2>
      <div class="row">
        <mat-form-field subscriptSizing="dynamic">
          <mat-label>Name</mat-label>
          <input matInput [(ngModel)]="newName" placeholder="e.g. Java developer" />
        </mat-form-field>
        <input #file type="file" accept=".docx,.doc,.pdf" (change)="picked($event)" hidden />
        <button mat-stroked-button (click)="file.click()"><mat-icon>attach_file</mat-icon> {{ chosen()?.name ?? 'Choose Word or PDF file' }}</button>
        <button mat-flat-button (click)="upload(file)" [disabled]="!chosen() || uploading()"><mat-icon>upload</mat-icon> {{ uploading() ? 'Reading…' : 'Upload' }}</button>
      </div>
    </div>

    @if (resumes().length === 0) {
      <div class="panel empty">No resumes yet. Upload your Java, QA/SDET or Angular resume to get started.</div>
    } @else {
      <div class="table-wrap">
        <table class="data">
          <thead><tr><th>Resume</th><th>Top skills</th><th>Experience</th><th>Used by</th><th>Uploaded</th><th></th></tr></thead>
          <tbody>
            @for (r of resumes(); track r.id) {
              <tr [class.open]="previewId() === r.id">
                <td><b>{{ r.name }}</b> @if (r.is_default) { <span class="tag good">default</span> }
                  @if (r.design) { <span class="tag info">{{ r.design }} design</span> }
                  @if (r.source_ext === '.pdf') { <span class="tag" matTooltip="Converted to Word once so it can be tailored">from PDF</span> }
                  <div class="muted small">{{ r.original_name }} · {{ r.text_chars | number }} chars</div></td>
                <td class="skills">@for (k of r.top_skills ?? []; track k) { <span class="tag info">{{ k }}</span> }</td>
                <td class="small">{{ yearsLabel(r) }}</td>
                <td class="small">{{ r.used_by }} profile(s)</td>
                <td class="small">{{ r.uploaded_at + 'Z' | date: 'MMM d, y' }}</td>
                <td class="act-cell"><div class="actions nowrap">
                  <button mat-flat-button (click)="suggest(r)" matTooltip="Suggest job titles, exclude words and settings from this resume">
                    <mat-icon>auto_awesome</mat-icon> Suggest keywords
                  </button>
                  <button mat-stroked-button (click)="check(r)" matTooltip="Recruiter and ATS checklist"><mat-icon>fact_check</mat-icon> Check</button>
                  <button mat-stroked-button (click)="designs(r)" matTooltip="Same content in a cleaner layout; you pick"><mat-icon>style</mat-icon> Designs</button>
                  @if (!r.is_default) { <button mat-button (click)="makeDefault(r)">Set default</button> }
                  <button mat-button (click)="preview(r)">{{ previewId() === r.id ? 'Hide' : 'View text' }}</button>
                  <button mat-button (click)="rename(r)">Rename</button>
                  <a mat-icon-button [href]="'/api/resumes/' + r.id + '/file'" matTooltip="Download"><mat-icon>download</mat-icon></a>
                  <button mat-icon-button (click)="remove(r)" matTooltip="Delete"><mat-icon>delete</mat-icon></button>
                </div></td>
              </tr>
              @if (previewId() === r.id) {
                <tr class="open"><td colspan="6">
                  <p class="muted small">This is the text the app compares with each job description. If something is missing here, the .docx may use text boxes or images.</p>
                  <div class="jd">{{ previewText() }}</div>
                </td></tr>
              }
            }
          </tbody>
        </table>
      </div>
    }
  `,
  styles: `
    .skills { max-width: 360px; }
    .act-cell { width: 1%; }
    .nowrap { white-space: nowrap; flex-wrap: nowrap; }
  `,
})
export class ResumesPage {
  private dialog = inject(MatDialog);
  private router = inject(Router);
  protected api = inject(Api);
  protected resumes = signal<Resume[]>([]);
  protected chosen = signal<File | null>(null);
  protected uploading = signal(false);
  protected previewId = signal<number | null>(null);
  protected previewText = signal('');
  protected newName = '';

  constructor() {
    this.load();
  }

  async load() {
    this.resumes.set(await this.api.get<Resume[]>('/resumes'));
  }

  picked(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0] ?? null;
    this.chosen.set(f);
    if (f && !this.newName) this.newName = f.name.replace(/\.(docx|doc|pdf)$/i, '');
  }

  async upload(input: HTMLInputElement) {
    const f = this.chosen();
    if (!f) return;
    const form = new FormData();
    form.append('file', f);
    form.append('name', this.newName);
    this.uploading.set(true);
    try {
      const r = await this.api.post<Resume>('/resumes', form);
      this.api.toast(r.source_ext === '.pdf'
        ? 'PDF resume read and converted to Word. Tip: press Designs for a clean layout.'
        : 'Resume uploaded');
      this.chosen.set(null);
      this.newName = '';
      input.value = '';
      this.load();
    } finally {
      this.uploading.set(false);
    }
  }

  check(r: Resume) {
    openResumeCheck(this.dialog, r, (n) => this.afterNewDesign(n));
  }

  designs(r: Resume) {
    openResumeDesigns(this.dialog, r, (n) => this.afterNewDesign(n));
  }

  private afterNewDesign(n: Resume) {
    this.api.toast(`Saved "${n.name}". Your original resume is unchanged.`);
    this.load();
  }

  yearsLabel(r: Resume) {
    return r.years_estimate === null || r.years_estimate === undefined ? 'no work dates found' : `about ${r.years_estimate} yrs`;
  }

  suggest(r: Resume) {
    const ref = this.dialog.open<SuggestDialog, unknown, SuggestResult>(SuggestDialog, {
      data: { resumeId: r.id }, width: '760px', maxWidth: '95vw', autoFocus: false,
    });
    ref.afterClosed().subscribe((res) => res && this.applySuggestions(r, res));
  }

  private async applySuggestions(r: Resume, res: SuggestResult) {
    const limits = res.max_years !== null ? { max_years: res.max_years, experience_levels: res.experience_levels ?? [] } : {};
    let profile: Profile;
    if (res.target.kind === 'new') {
      profile = await this.api.post<Profile>('/profiles', {
        name: res.target.name, keywords: res.keywords, exclude: res.exclude, must_include: res.must_include,
        resume_id: r.id, sites: ['linkedin', 'indeed', 'dice'], posted_within: '24h', enabled: true, ...limits,
      });
      this.api.toast(`Profile "${profile.name}" created. Add your locations, then Save & run.`);
    } else if (res.target.kind === 'existing') {
      const cur = await this.api.get<Profile>(`/profiles/${res.target.id}`);
      profile = await this.api.put<Profile>(`/profiles/${cur.id}`, {
        keywords: mergeList(cur.keywords, res.keywords), exclude: mergeList(cur.exclude, res.exclude),
        must_include: mergeList(cur.must_include, res.must_include), ...limits,
      });
      this.api.toast(`Added to "${profile.name}".`);
    } else {
      return;
    }
    this.router.navigate(['/profiles', profile.id]);
  }

  async makeDefault(r: Resume) {
    await this.api.post(`/resumes/${r.id}/default`);
    this.load();
  }

  async preview(r: Resume) {
    if (this.previewId() === r.id) return this.previewId.set(null);
    const full = await this.api.get<Resume>(`/resumes/${r.id}`);
    this.previewText.set(full.text ?? '');
    this.previewId.set(r.id);
  }

  async rename(r: Resume) {
    const name = prompt('New name', r.name);
    if (!name?.trim()) return;
    await this.api.put(`/resumes/${r.id}`, { name });
    this.load();
  }

  async remove(r: Resume) {
    if (!confirm(`Delete resume "${r.name}"? Profiles using it will need another resume.`)) return;
    await this.api.delete(`/resumes/${r.id}`);
    this.load();
  }
}

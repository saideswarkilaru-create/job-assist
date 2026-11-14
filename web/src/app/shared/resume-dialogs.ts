import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Api, Resume } from '../api';

interface CheckItem { level: 'good' | 'tip' | 'fix'; title: string; detail: string; }
interface CheckResult { score: number; items: CheckItem[]; words: number; }
interface Design { key: string; label: string; about: string; ok: boolean; check: string; preview: string | null; }

/** Resume check: what a recruiter and an ATS would flag. */
@Component({
  selector: 'app-resume-check-dialog',
  imports: [MatDialogModule, MatButtonModule, MatIconModule, MatProgressBarModule],
  template: `
    <h2 mat-dialog-title>Resume check: {{ data.resume.name }}</h2>
    <mat-dialog-content>
      @if (!r()) {
        <p class="muted">Checking…</p><mat-progress-bar mode="indeterminate" />
      } @else {
        @let res = r()!;
        <div class="score-row">
          <span class="big" [class]="res.score >= 80 ? 'big good' : res.score >= 60 ? 'big mid' : 'big low'">{{ res.score }}</span>
          <span class="muted">out of 100 · what recruiters and applicant-tracking systems look for. Suggestions only; nothing is changed.</span>
        </div>
        @for (i of res.items; track i.title) {
          <div class="item">
            <mat-icon [class]="i.level">{{ i.level === 'good' ? 'check_circle' : i.level === 'tip' ? 'lightbulb' : 'error' }}</mat-icon>
            <div><b>{{ i.title }}</b>@if (i.detail) { <div class="muted small">{{ i.detail }}</div> }</div>
          </div>
        }
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Close</button>
      <button mat-flat-button (click)="designs()"><mat-icon>style</mat-icon> Choose a design</button>
    </mat-dialog-actions>
  `,
  styles: `
    .score-row { display: flex; align-items: center; gap: 14px; margin-bottom: 10px; }
    .big { font-size: 34px; font-weight: 700; }
    .big.good { color: var(--good); } .big.mid { color: var(--warn); } .big.low { color: var(--bad); }
    .item { display: flex; gap: 10px; align-items: flex-start; padding: 7px 0; border-bottom: 1px solid var(--line); }
    mat-icon.good { color: var(--good); } mat-icon.tip { color: var(--warn); } mat-icon.fix { color: var(--bad); }
  `,
})
export class ResumeCheckDialog {
  protected data = inject<{ resume: Resume }>(MAT_DIALOG_DATA);
  private api = inject(Api);
  private ref = inject(MatDialogRef<ResumeCheckDialog>);
  protected r = signal<CheckResult | null>(null);

  constructor() {
    this.api.get<CheckResult>(`/resumes/${this.data.resume.id}/check`).then((x) => this.r.set(x), () => this.ref.close());
  }

  designs() {
    this.ref.close('designs');
  }
}

/** Resume designs: same content, three ATS-friendly layouts; the user picks one. */
@Component({
  selector: 'app-resume-designs-dialog',
  imports: [FormsModule, MatDialogModule, MatButtonModule, MatCheckboxModule, MatFormFieldModule, MatIconModule,
    MatInputModule, MatProgressBarModule],
  template: `
    <h2 mat-dialog-title>Pick a resume design</h2>
    <mat-dialog-content>
      <p class="muted small">Your exact words in a cleaner layout: one column, standard fonts, no tables or text boxes,
        so every applicant-tracking system can read it. Links stay clickable. Your original resume is kept as it is.</p>
      @if (!designs()) {
        <p class="muted">Preparing previews (about 10–20 seconds)…</p><mat-progress-bar mode="indeterminate" />
      } @else {
        <div class="grid">
          @for (d of designs()!; track d.key) {
            <div class="card" [class.picked]="picked() === d.key" (click)="pick(d)">
              <div class="head"><b>{{ d.label }}</b>
                @if (picked() === d.key) { <mat-icon class="tick">check_circle</mat-icon> }</div>
              <div class="muted small about">{{ d.about }}</div>
              @if (d.preview) {
                <iframe [src]="safe(d.preview)" title="{{ d.label }} preview"></iframe>
              } @else {
                <div class="nopreview muted small">No preview available on this PC, but the Word file is ready.</div>
              }
              @if (!d.ok) { <div class="tag bad">Not offered: {{ d.check }}</div> }
            </div>
          }
        </div>
        @if (picked()) {
          <div class="row save">
            <mat-form-field subscriptSizing="dynamic" class="name">
              <mat-label>Name for the new resume</mat-label>
              <input matInput [(ngModel)]="newName" />
            </mat-form-field>
            <mat-checkbox [(ngModel)]="makeDefault">Make it my default resume</mat-checkbox>
          </div>
        }
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-flat-button [disabled]="!picked() || saving()" (click)="use()">Use this design</button>
    </mat-dialog-actions>
  `,
  styles: `
    .grid { display: grid; grid-template-columns: repeat(3, minmax(220px, 1fr)); gap: 12px; }
    .card { border: 2px solid var(--line); border-radius: 10px; padding: 10px; cursor: pointer; background: var(--panel); }
    .card.picked { border-color: var(--accent); }
    .head { display: flex; justify-content: space-between; align-items: center; }
    .tick { color: var(--accent); }
    .about { min-height: 34px; margin: 4px 0 8px; }
    iframe { width: 100%; height: 420px; border: 1px solid var(--line); border-radius: 6px; pointer-events: none; background: #fff; }
    .nopreview { height: 120px; display: flex; align-items: center; justify-content: center; text-align: center; }
    .save { margin-top: 14px; }
    .name { width: 360px; }
  `,
})
export class ResumeDesignsDialog {
  protected data = inject<{ resume: Resume }>(MAT_DIALOG_DATA);
  private api = inject(Api);
  private ref = inject(MatDialogRef<ResumeDesignsDialog, Resume>);
  private sanitizer = inject(DomSanitizer);
  protected designs = signal<Design[] | null>(null);
  protected picked = signal<string | null>(null);
  protected saving = signal(false);
  protected newName = '';
  protected makeDefault = true;
  private urls = new Map<string, SafeResourceUrl>();

  constructor() {
    this.api.post<{ designs: Design[] }>(`/resumes/${this.data.resume.id}/designs`).then(
      (r) => this.designs.set(r.designs.filter((d) => d.ok)),
      () => this.ref.close(),
    );
  }

  safe(url: string): SafeResourceUrl {
    if (!this.urls.has(url)) {
      this.urls.set(url, this.sanitizer.bypassSecurityTrustResourceUrl(`${url}?t=${Date.now()}#toolbar=0&navpanes=0&view=FitH`));
    }
    return this.urls.get(url)!;
  }

  pick(d: Design) {
    this.picked.set(d.key);
    this.newName = `${this.data.resume.name} (${d.label})`;
  }

  async use() {
    this.saving.set(true);
    try {
      const r = await this.api.post<Resume>(`/resumes/${this.data.resume.id}/designs/${this.picked()}/use`,
        { name: this.newName, make_default: this.makeDefault });
      this.ref.close(r);
    } finally {
      this.saving.set(false);
    }
  }
}

/** Open the check, and chain into designs if the user asks. */
export function openResumeCheck(dialog: MatDialog, resume: Resume, onNew: (r: Resume) => void) {
  dialog.open(ResumeCheckDialog, { data: { resume }, width: '640px', maxWidth: '95vw', autoFocus: false })
    .afterClosed().subscribe((res) => res === 'designs' && openResumeDesigns(dialog, resume, onNew));
}

export function openResumeDesigns(dialog: MatDialog, resume: Resume, onNew: (r: Resume) => void) {
  dialog.open<ResumeDesignsDialog, unknown, Resume>(ResumeDesignsDialog, {
    data: { resume }, width: '1100px', maxWidth: '96vw', autoFocus: false,
  }).afterClosed().subscribe((r) => r && onNew(r));
}

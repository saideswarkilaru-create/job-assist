import { Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api } from '../api';

interface Application {
  id: number; job_id: number; applied_at: string; status: string; resume_file: string | null;
  follow_up_on: string | null; response_at: string | null; notes: string; channel: string;
  history: { status: string; at: string; note: string }[];
  title: string; company: string; location: string; site: string; url: string; match_score: number | null;
  follow_up_due: number; days_since: number;
}
interface AppList { items: Application[]; counts: Record<string, number>; statuses: string[]; }

@Component({
  selector: 'app-applications',
  imports: [DatePipe, FormsModule, MatButtonModule, MatFormFieldModule, MatIconModule, MatInputModule, MatSelectModule, MatTooltipModule],
  template: `
    <div class="page-head">
      <div class="grow">
        <h1>Applications</h1>
        <p class="sub">Every job you applied to, where it stands, and when to follow up. Update the status as you hear back.</p>
      </div>
      <a mat-stroked-button href="/api/applications.csv"><mat-icon>download</mat-icon> Export CSV</a>
    </div>

    @if (data(); as d) {
      <div class="chips">
        <button class="chip" [class.on]="!filter" (click)="setFilter('')">All <b>{{ total(d) }}</b></button>
        <button class="chip" [class.on]="filter === 'active'" (click)="setFilter('active')">In progress <b>{{ (d.counts['Applied'] || 0) + (d.counts['Screening'] || 0) + (d.counts['Interview'] || 0) }}</b></button>
        @for (s of d.statuses; track s) {
          <button class="chip" [class.on]="filter === s" (click)="setFilter(s)">{{ s }} <b>{{ d.counts[s] || 0 }}</b></button>
        }
        @if (d.counts['follow_up_due']) { <span class="tag warn due">{{ d.counts['follow_up_due'] }} follow-up(s) due</span> }
        <mat-form-field subscriptSizing="dynamic" class="search">
          <mat-label>Search company / role</mat-label>
          <input matInput [(ngModel)]="q" (keyup.enter)="load()" />
        </mat-form-field>
      </div>

      @if (!d.items.length) {
        <div class="panel empty">
          Nothing here yet. On <b>Today</b>, open a job and press <b>Mark as applied</b> after you apply.
        </div>
      } @else {
        <div class="table-wrap">
          <table class="data">
            <thead><tr><th>Job</th><th>Applied</th><th>Status</th><th>Follow up</th><th>Resume sent</th><th>Notes</th><th></th></tr></thead>
            <tbody>
              @for (a of d.items; track a.id) {
                <tr [class.due]="a.follow_up_due">
                  <td class="job">
                    <a [href]="a.url" target="_blank" rel="noopener" class="title">{{ a.title }}</a>
                    <div class="muted small">{{ a.company }} · {{ a.location }} · {{ a.site }}@if (a.match_score !== null) { · score {{ a.match_score }} }</div>
                  </td>
                  <td class="small nowrap">{{ a.applied_at + 'Z' | date: 'MMM d, y' }}<div class="muted">{{ a.days_since }} day(s) ago</div>
                    @if (a.channel) { <div class="muted">{{ channelLabel(a.channel) }}</div> }</td>
                  <td>
                    <mat-select class="status" [value]="a.status" (selectionChange)="update(a, { status: $event.value })"
                      [matTooltip]="historyText(a)">
                      @for (s of d.statuses; track s) { <mat-option [value]="s">{{ s }}</mat-option> }
                    </mat-select>
                  </td>
                  <td class="nowrap">
                    <input type="date" class="date" [value]="a.follow_up_on || ''" (change)="update(a, { follow_up_on: $any($event.target).value })" />
                    @if (a.follow_up_due) { <div class="tag warn">due</div> }
                  </td>
                  <td class="small">@if (a.resume_file) {
                    <a [href]="'/api/jobs/' + a.job_id + '/file/' + (a.resume_file.toLowerCase().endsWith('.pdf') ? 'pdf' : 'docx')">{{ fileName(a.resume_file) }}</a>
                  }</td>
                  <td><textarea class="notes" rows="2" [value]="a.notes" placeholder="recruiter name, next step…"
                        (change)="update(a, { notes: $any($event.target).value })"></textarea></td>
                  <td class="nowrap">
                    <a mat-icon-button [href]="a.url" target="_blank" rel="noopener" matTooltip="Open the job posting"><mat-icon>open_in_new</mat-icon></a>
                    <button mat-icon-button (click)="undo(a)" matTooltip="Undo: I didn't apply"><mat-icon>undo</mat-icon></button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        <p class="muted small">Tip: follow up politely about {{ followDays() }} days after applying if you haven't heard back.
          The follow-up date is set automatically (Settings → Follow-up reminder).</p>
      }
    }
  `,
  styles: `
    .chips { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 14px; }
    .chip { border: 1px solid var(--line); background: var(--panel); border-radius: 16px; padding: 6px 12px; cursor: pointer; font: inherit; }
    .chip.on { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
    .due { margin-left: 6px; }
    .search { margin-left: auto; width: 220px; }
    tr.due td { background: var(--warn-soft); }
    .job { min-width: 240px; } .title { font-weight: 600; text-decoration: none; }
    .status { width: 130px; }
    .date { font: inherit; padding: 4px; border: 1px solid var(--line); border-radius: 6px; }
    .notes { font: inherit; font-size: 12px; width: 220px; border: 1px solid var(--line); border-radius: 6px; padding: 4px; }
    .nowrap { white-space: nowrap; }
  `,
})
export class ApplicationsPage {
  private api = inject(Api);
  protected data = signal<AppList | null>(null);
  protected followDays = signal(7);
  protected filter = '';
  protected q = '';

  constructor() {
    this.load();
    this.api.get<{ values: Record<string, unknown> }>('/settings').then((s) => this.followDays.set(Number(s.values['follow_up_days']) || 7));
  }

  async load() {
    this.data.set(await this.api.get<AppList>('/applications', { status: this.filter, q: this.q }));
  }

  setFilter(f: string) {
    this.filter = f;
    this.load();
  }

  total(d: AppList) {
    return d.statuses.reduce((n, s) => n + (d.counts[s] || 0), 0);
  }

  async update(a: Application, change: Record<string, unknown>) {
    await this.api.patch(`/applications/${a.id}`, change);
    if ('status' in change) this.api.toast(`${a.company}: ${change['status']}`);
    this.load();
  }

  async undo(a: Application) {
    if (!confirm(`Remove "${a.title}" at ${a.company} from your applications?`)) return;
    await this.api.delete(`/applications/${a.id}`);
    this.load();
  }

  fileName(p: string) {
    return p.split(/[\\/]/).pop();
  }

  channelLabel(c: string) {
    return ({ easy_apply: 'Easy Apply', company_site: 'Company site', email: 'Email', referral: 'Referral', other: 'Other' } as Record<string, string>)[c] ?? c;
  }

  historyText(a: Application) {
    return a.history.map((h) => `${h.status}${h.at ? ' · ' + h.at.slice(0, 10) : ''}${h.note ? ' · ' + h.note : ''}`).join('\n');
  }
}

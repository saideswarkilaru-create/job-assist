import { Component, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { Api, Run } from '../api';

/** Shown at the top of every page while a filled application waits for the person. */
@Component({
  selector: 'app-apply-review',
  imports: [MatButtonModule, MatIconModule],
  template: `
    @if (run(); as r) {
      @if (r.payload; as p) {
        <div class="card">
          <div class="head">
            <mat-icon>assignment</mat-icon>
            <div class="grow">
              <b>Review your application: {{ p.title }} at {{ p.company }}</b>
              <div class="small">The form is filled in the browser window, with the
                @if (p.final_button) { <b>"{{ p.final_button }}"</b> button outlined in red. }
                @else { submit button not found yet. }
                Nothing has been sent.</div>
            </div>
            <button mat-button (click)="open.set(!open())">{{ open() ? 'Hide details' : 'Show details' }}</button>
          </div>
          @if (p.note) { <div class="note">{{ p.note }}</div> }
          @if (p.needs_you.length) {
            <div class="needs"><b>Needs you ({{ p.needs_you.length }})</b> — answer these in the browser window:
              <ul>@for (n of p.needs_you; track $index) { <li><b>{{ n.label || 'Unlabelled field' }}</b> <span class="muted">· {{ n.why }}</span></li> }</ul>
            </div>
          }
          @if (open()) {
            <div class="filled"><b>Filled by the app ({{ p.filled.length }})</b>
              <ul>@for (f of p.filled; track $index) { <li>{{ f.label }}: <b>{{ f.value }}</b> <span class="muted">({{ f.source }})</span></li> }</ul>
              @if (p.kept.length) { <div class="muted small">Left as the site had them: {{ keptText(p) }}</div> }
              @if (p.resume) { <div class="small">Resume attached: <b>{{ p.resume }}</b></div> }
            </div>
          }
          <div class="actions">
            <button mat-flat-button [disabled]="!p.final_button || busy()" (click)="send('submit')">
              <mat-icon>send</mat-icon> Approve &amp; Submit
            </button>
            <button mat-stroked-button [disabled]="busy()" (click)="send('done')">I submitted it myself</button>
            <button mat-button [disabled]="busy()" (click)="send('refill')">Fill this page again</button>
            <button mat-button [disabled]="busy()" (click)="send('cancel')">Cancel, don't apply</button>
          </div>
        </div>
      }
    }
  `,
  styles: `
    .card { margin: 12px 24px 0; padding: 14px 16px; border: 2px solid var(--accent); border-radius: 12px; background: var(--panel); }
    .head { display: flex; gap: 10px; align-items: flex-start; } .grow { flex: 1; }
    .note { margin-top: 8px; padding: 8px 10px; border-radius: 8px; background: var(--warn-soft); font-size: 13px; }
    .needs { margin-top: 8px; padding: 8px 10px; border-radius: 8px; background: var(--warn-soft); font-size: 13px; }
    .filled { margin-top: 8px; font-size: 13px; }
    ul { margin: 4px 0; padding-left: 18px; }
    .actions { margin-top: 10px; }
  `,
})
export class ApplyReview {
  private api = inject(Api);
  protected open = signal(false);
  protected busy = signal(false);
  protected run = computed<Run | null>(() =>
    this.api.activeRuns().find((r) => (r.kind === 'apply' || r.kind === 'tailor_apply') && !!r.payload) ?? null);

  async send(command: 'submit' | 'done' | 'refill' | 'cancel') {
    const r = this.run();
    if (!r) return;
    if (command === 'submit' && !confirm(`Submit your application to ${r.payload!.company} now?\n\nThe app will press "${r.payload!.final_button}" for you.`)) return;
    if (command === 'done' && !confirm('Did you press Submit on the site and see a confirmation?')) return;
    this.busy.set(true);
    try {
      await this.api.post(`/runs/${r.id}/command`, { command });
      this.api.toast({ submit: 'Submitting…', done: 'Logging it in Applications…', refill: 'Filling again…', cancel: 'Cancelled. Nothing was sent.' }[command]);
      setTimeout(() => this.api.refreshRuns(), 1500);
    } finally {
      setTimeout(() => this.busy.set(false), 2500);
    }
  }

  keptText(p: NonNullable<Run['payload']>) {
    return p.kept.map((k) => k.label).filter(Boolean).slice(0, 8).join(', ');
  }
}

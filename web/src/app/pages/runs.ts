import { Component, DestroyRef, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { Api, Run } from '../api';

@Component({
  selector: 'app-runs',
  imports: [DatePipe, MatButtonModule, MatIconModule],
  template: `
    <div class="page-head"><div class="grow">
      <h1>Runs &amp; logs</h1>
      <p class="sub">Every search, analysis and Tailor &amp; Apply run, with its full log.</p>
    </div></div>
    <div class="layout">
      <div class="table-wrap list">
        <table class="data">
          <thead><tr><th>#</th><th>What</th><th>Status</th><th>Found</th><th>Started</th></tr></thead>
          <tbody>
            @for (r of runs(); track r.id) {
              <tr [class.open]="sel() === r.id" (click)="select(r)" class="click">
                <td>{{ r.id }}</td>
                <td>{{ kind(r) }}<div class="muted small">{{ r.profile_name || r.job_title || '' }}</div></td>
                <td><span [class]="tone(r.status)">{{ r.status }}</span></td>
                <td class="small">{{ r.jobs_matched }} / {{ r.jobs_seen }}</td>
                <td class="small">{{ r.started_at + 'Z' | date: 'MMM d, h:mm:ss a' }}</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
      <div>
        @if (current(); as r) {
          <div class="row" style="margin-bottom:10px">
            <h2 style="margin:0">Run #{{ r.id }}</h2>
            <span class="muted">{{ r.message }}</span>
            <span style="flex:1"></span>
            @if (isActive(r)) { <button mat-stroked-button (click)="stop(r)"><mat-icon>stop</mat-icon> Stop</button> }
          </div>
          <pre class="log">{{ log() || 'No log output yet.' }}</pre>
        } @else {
          <div class="panel empty">Pick a run to see its log.</div>
        }
      </div>
    </div>
  `,
  styles: `
    .layout { display: grid; grid-template-columns: minmax(360px, 1fr) 2fr; gap: 16px; align-items: start; }
    .click { cursor: pointer; }
  `,
})
export class RunsPage {
  protected api = inject(Api);
  protected runs = signal<Run[]>([]);
  protected sel = signal<number | null>(null);
  protected current = signal<Run | null>(null);
  protected log = signal('');

  constructor() {
    this.refresh(true);
    const t = setInterval(() => this.refresh(false), 3000);
    inject(DestroyRef).onDestroy(() => clearInterval(t));
  }

  private async refresh(first: boolean) {
    const runs = await this.api.get<Run[]>('/runs');
    this.runs.set(runs);
    if (first && runs.length) this.sel.set(runs[0].id);
    const id = this.sel();
    if (id) {
      const r = runs.find((x) => x.id === id) ?? null;
      this.current.set(r);
      if (r && (first || this.isActive(r) || !this.log())) this.log.set(await this.api.text(`/runs/${id}/log`));
    }
  }

  async select(r: Run) {
    this.sel.set(r.id);
    this.current.set(r);
    this.log.set(await this.api.text(`/runs/${r.id}/log`));
  }

  isActive(r: Run) {
    return ['queued', 'running', 'waiting_user'].includes(r.status);
  }

  kind(r: Run) {
    return this.api.meta()?.run_kinds[r.kind] ?? r.kind;
  }

  tone(s: string) {
    return 'tag ' + ({ done: 'good', failed: 'bad', cancelled: '', waiting_user: 'warn', running: 'info', queued: 'info' } as Record<string, string>)[s];
  }

  async stop(r: Run) {
    await this.api.post(`/runs/${r.id}/stop`);
    this.api.toast('Stopping after the current step…');
  }
}

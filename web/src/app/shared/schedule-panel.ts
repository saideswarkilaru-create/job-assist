import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { Api } from '../api';

interface Schedule { enabled: boolean; supported: boolean; time: string; next_run?: string; last_run?: string;
  last_result?: string; state?: string; command: string; task_name: string; }

@Component({
  selector: 'app-schedule-panel',
  imports: [FormsModule, MatButtonModule, MatIconModule, MatSlideToggleModule],
  template: `
    <div class="panel">
      <h2>Daily search</h2>
      @if (s(); as s) {
        <div class="row">
          <mat-slide-toggle [checked]="s.enabled" (change)="set($event.checked)" [disabled]="busy() || !s.supported">
            Search all enabled profiles every day at
          </mat-slide-toggle>
          <input type="time" class="time" [(ngModel)]="time" (change)="s.enabled && set(true)" />
        </div>
        <p class="small" [class.muted]="!s.enabled">
          @if (s.enabled) {
            On. Next run: <b>{{ s.next_run || '…' }}</b>
            @if (s.last_run && !s.last_run.startsWith('N/A') && !s.last_run.includes('1999')) { · last run {{ s.last_run }} }
          } @else {
            Off. Turn it on and Windows starts the search for you each day (even if the app isn't open).
            If the laptop is asleep at that time, it runs as soon as it wakes up.
          }
        </p>
        <p class="muted small">You need to be signed in to Windows for it to run (the browser has to be visible for logins and captchas).
          When it finishes you get a notification, plus a reminder if any follow-ups are due.</p>
        <div class="actions">
          <button mat-stroked-button (click)="testToast()"><mat-icon>notifications</mat-icon> Send a test notification</button>
          <button mat-button (click)="showCmd.set(!showCmd())">{{ showCmd() ? 'Hide' : 'Show' }} the exact Task Scheduler command</button>
        </div>
        @if (showCmd()) {
          <p class="muted small">To set it up yourself instead, paste this into PowerShell or Command Prompt:</p>
          <pre class="cmd">{{ s.command }}</pre>
          <button mat-button (click)="copy(s.command)"><mat-icon>content_copy</mat-icon> Copy</button>
          <p class="muted small">To remove it: <code>schtasks /Delete /F /TN "{{ s.task_name }}"</code>.
            (The switch above also makes it catch up after sleep, which the plain command can't.)</p>
        }
      }
    </div>
  `,
  styles: `
    .time { font: inherit; padding: 6px 8px; border: 1px solid var(--line); border-radius: 6px; }
    .cmd { background: #14171c; color: #d7dde6; padding: 10px; border-radius: 8px; white-space: pre-wrap; word-break: break-all; font-size: 12px; }
  `,
})
export class SchedulePanel {
  private api = inject(Api);
  protected s = signal<Schedule | null>(null);
  protected busy = signal(false);
  protected showCmd = signal(false);
  protected time = '08:00';

  constructor() {
    this.load();
  }

  async load() {
    const s = await this.api.get<Schedule>('/schedule');
    this.time = s.time;
    this.s.set(s);
  }

  async set(enabled: boolean) {
    this.busy.set(true);
    try {
      const s = await this.api.post<Schedule>('/schedule', { enabled, time: this.time });
      this.s.set(s);
      this.time = s.time;
      this.api.toast(enabled ? `Daily search is on at ${s.time}.` : 'Daily search is off.');
    } catch {
      this.load();
    } finally {
      this.busy.set(false);
    }
  }

  async testToast() {
    await this.api.post('/notify/test');
    this.api.toast('Sent. You should see it in the corner of your screen.');
  }

  async copy(text: string) {
    await navigator.clipboard.writeText(text);
    this.api.toast('Copied');
  }
}

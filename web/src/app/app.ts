import { Component, DestroyRef, computed, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Api, Run } from './api';
import { ApplyReview } from './shared/apply-review';

@Component({
  selector: 'app-root',
  imports: [
    RouterOutlet, RouterLink, RouterLinkActive, MatButtonModule, MatIconModule,
    MatSidenavModule, MatToolbarModule, MatTooltipModule, MatProgressBarModule, ApplyReview,
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected api = inject(Api);
  protected nav = [
    { path: '/today', label: 'Today', icon: 'today' },
    { path: '/profiles', label: 'Profiles', icon: 'manage_search' },
    { path: '/sources', label: 'Companies & Sites', icon: 'apartment' },
    { path: '/resumes', label: 'Resumes', icon: 'description' },
    { path: '/my-details', label: 'My details', icon: 'badge' },
    { path: '/applications', label: 'Applications', icon: 'assignment_turned_in' },
    { path: '/stats', label: 'Stats', icon: 'insights' },
    { path: '/runs', label: 'Runs & logs', icon: 'terminal' },
    { path: '/settings', label: 'Settings', icon: 'settings' },
  ];
  protected run = computed<Run | null>(() => this.api.activeRuns()[0] ?? null);
  protected waiting = computed(() => this.api.activeRuns().find((r) => r.status === 'waiting_user' && !r.payload) ?? null);

  constructor() {
    this.api.loadMeta();
    this.api.refreshRuns();
    const t = setInterval(() => this.api.refreshRuns(), 3000);
    inject(DestroyRef).onDestroy(() => clearInterval(t));
  }

  protected label(r: Run): string {
    const kind = this.api.meta()?.run_kinds[r.kind] ?? r.kind;
    const what = r.profile_name ?? r.job_title ?? (r.kind === 'search' ? 'all enabled profiles' : '');
    return `${kind}${what ? ': ' + what : ''}`;
  }

  async runAll() {
    await this.api.post('/runs/search-all');
    this.api.toast('Started: all enabled profiles. A browser window will open.');
    this.api.refreshRuns();
  }

  async login() {
    await this.api.post('/runs/login');
    this.api.toast('Browser opened. Log in to each site yourself, then close the window.');
    this.api.refreshRuns();
  }

  async stop(r: Run) {
    await this.api.post(`/runs/${r.id}/stop`);
    this.api.toast('Stopping after the current step…');
  }
}

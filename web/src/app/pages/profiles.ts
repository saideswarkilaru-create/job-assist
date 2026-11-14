import { Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api, Profile } from '../api';

@Component({
  selector: 'app-profiles',
  imports: [DatePipe, RouterLink, MatButtonModule, MatIconModule, MatSlideToggleModule, MatTooltipModule],
  template: `
    <div class="page-head">
      <div class="grow">
        <h1>Search profiles</h1>
        <p class="sub">Each profile is one saved search: keywords, locations, sites and the resume to match against.</p>
      </div>
      <a mat-flat-button routerLink="/profiles/new"><mat-icon>add</mat-icon> New profile</a>
    </div>

    @if (profiles().length === 0) {
      <div class="panel empty">No profiles yet. Create one like "Java USA" or "SDET India".</div>
    }
    <div class="cards">
      @for (p of profiles(); track p.id) {
        <div class="panel card" [class.off]="!p.enabled">
          <div class="row top">
            <a [routerLink]="['/profiles', p.id]" class="name">{{ p.name }}</a>
            <span class="spacer"></span>
            <mat-slide-toggle [checked]="p.enabled" (change)="toggle(p, $event.checked)" matTooltip="Include in Run all / daily run" />
          </div>
          <div class="tags">
            @for (k of p.keywords; track k) { <span class="tag info">{{ k }}</span> }
            @for (k of p.exclude; track k) { <span class="tag bad">−{{ k }}</span> }
          </div>
          <div class="muted small">
            {{ p.locations.length ? p.locations.join(' · ') : 'Any location' }}
            @if (p.work_modes.length) { · {{ p.work_modes.join('/') }} }
            · {{ postedLabel(p.posted_within) }}
          </div>
          <div class="muted small">Sites: {{ p.sites.join(', ') || 'none' }} · min score {{ p.min_score }} · max {{ p.max_jobs }}/run</div>
          <div class="muted small">{{ p.jobs_matched || 0 }} jobs matched ·
            last run {{ p.last_run_at ? (p.last_run_at + 'Z' | date: 'MMM d, h:mm a') : 'never' }}</div>
          <div class="actions">
            <button mat-flat-button (click)="run(p)" [disabled]="api.activeRuns().length > 0"><mat-icon>play_arrow</mat-icon> Run this profile now</button>
            <a mat-button [routerLink]="['/profiles', p.id]"><mat-icon>edit</mat-icon> Edit</a>
            <button mat-button (click)="duplicate(p)"><mat-icon>content_copy</mat-icon> Duplicate</button>
            <button mat-button (click)="remove(p)"><mat-icon>delete</mat-icon> Delete</button>
          </div>
        </div>
      }
    </div>
  `,
  styles: `
    .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 16px; }
    .card { display: flex; flex-direction: column; gap: 8px; margin: 0; }
    .card.off { opacity: .6; }
    .name { font-size: 16px; font-weight: 600; text-decoration: none; }
    .spacer { flex: 1; }
    .top { flex-wrap: nowrap; }
    .actions { margin-top: 6px; }
  `,
})
export class ProfilesPage {
  protected api = inject(Api);
  private router = inject(Router);
  protected profiles = signal<Profile[]>([]);

  constructor() {
    this.load();
  }

  async load() {
    this.profiles.set(await this.api.get<Profile[]>('/profiles'));
  }

  postedLabel(v: string) {
    return this.api.meta()?.posted_within.find((p) => p.value === v)?.label ?? v;
  }

  async toggle(p: Profile, enabled: boolean) {
    await this.api.put(`/profiles/${p.id}`, { enabled });
    this.load();
  }

  async run(p: Profile) {
    await this.api.post(`/profiles/${p.id}/run`);
    this.api.toast(`Running "${p.name}". A browser window will open; results appear on Today.`);
    this.api.refreshRuns();
  }

  async duplicate(p: Profile) {
    const copy = await this.api.post<Profile>(`/profiles/${p.id}/duplicate`);
    this.router.navigate(['/profiles', copy.id]);
  }

  async remove(p: Profile) {
    if (!confirm(`Delete profile "${p.name}"? Jobs it found stay in the database.`)) return;
    await this.api.delete(`/profiles/${p.id}`);
    this.load();
  }
}

import { Component, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSliderModule } from '@angular/material/slider';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { Api, Profile, Resume, Site } from '../api';
import { TagsInput } from '../shared/tags-input';
import { MatDialog } from '@angular/material/dialog';
import { SuggestDialog, SuggestResult, mergeList } from '../shared/suggest-dialog';

const BLANK: Profile = {
  name: '', enabled: true, keywords: [], must_include: [], must_include_mode: 'all', exclude: [],
  locations: [], work_modes: [], posted_within: '24h', job_types: [], experience_levels: [],
  sites: ['dice', 'linkedin', 'indeed'], resume_id: null, min_score: 60, max_jobs: 25, max_years: 3,
};

@Component({
  selector: 'app-profile-edit',
  imports: [
    FormsModule, RouterLink, MatButtonModule, MatButtonToggleModule, MatCheckboxModule, MatFormFieldModule,
    MatIconModule, MatInputModule, MatSelectModule, MatSliderModule, MatSlideToggleModule, TagsInput,
  ],
  template: `
    @if (p(); as p) {
      <div class="page-head">
        <div class="grow">
          <a routerLink="/profiles" class="small">← Profiles</a>
          <h1>{{ isNew() ? 'New profile' : p.name }}</h1>
        </div>
        <mat-slide-toggle [(ngModel)]="p.enabled">Enabled</mat-slide-toggle>
      </div>

      <div class="panel">
        <h2>Name</h2>
        <mat-form-field class="full">
          <mat-label>Profile name</mat-label>
          <input matInput [(ngModel)]="p.name" placeholder="e.g. Java USA" required />
        </mat-form-field>
      </div>

      <div class="panel">
        <h2>What to search</h2>
        <div class="row suggest-row">
          <span class="muted small">Not sure what to search?</span>
          <button mat-stroked-button (click)="suggest()" [disabled]="!p.resume_id">
            <mat-icon>auto_awesome</mat-icon> Suggest from my resume
          </button>
          @if (!p.resume_id) { <span class="muted small">(pick a base resume under Matching first)</span> }
        </div>
        <app-tags-input label="Search keywords" [(value)]="p.keywords"
          hint="Each keyword is a separate search, e.g. Java developer, SDET, Angular developer. 4–6 focused titles work best." />
        <div class="grid2">
          <div>
            <app-tags-input label="Must include" tone="must" [(value)]="p.must_include"
              hint="Job title or description must contain these" />
            <mat-button-toggle-group [(ngModel)]="p.must_include_mode" class="mode">
              <mat-button-toggle value="all">All of them</mat-button-toggle>
              <mat-button-toggle value="any">Any one of them</mat-button-toggle>
            </mat-button-toggle-group>
          </div>
          <app-tags-input label="Exclude" tone="exclude" [(value)]="p.exclude"
            hint="Skip jobs mentioning these, e.g. Senior Architect, Clearance required" />
        </div>
      </div>

      <div class="panel">
        <h2>Where and when</h2>
        <app-tags-input label="Locations" [(value)]="p.locations" [splitOnComma]="false"
          hint='Press Enter after each one, e.g. Dallas, TX · New Jersey · Remote. Leave empty for anywhere.' />
        <div class="grid2">
          <div>
            <div class="label">Work mode <span class="muted small">(none ticked = any)</span></div>
            @for (m of meta()?.work_modes ?? []; track m) {
              <mat-checkbox [checked]="p.work_modes.includes(m)" (change)="flip(p.work_modes, m)">{{ m }}</mat-checkbox>
            }
          </div>
          <mat-form-field>
            <mat-label>Posted within</mat-label>
            <mat-select [(ngModel)]="p.posted_within">
              @for (o of meta()?.posted_within ?? []; track o.value) { <mat-option [value]="o.value">{{ o.label }}</mat-option> }
            </mat-select>
          </mat-form-field>
        </div>
        <div class="grid2">
          <div>
            <div class="label">Job type <span class="muted small">(none ticked = any)</span></div>
            @for (t of meta()?.job_types ?? []; track t) {
              <mat-checkbox [checked]="p.job_types.includes(t)" (change)="flip(p.job_types, t)">{{ t }}</mat-checkbox>
            }
          </div>
          <div>
            <div class="label">Experience level <span class="muted small">(judged from the job title)</span></div>
            @for (t of meta()?.experience_levels ?? []; track t) {
              <mat-checkbox [checked]="p.experience_levels.includes(t)" (change)="flip(p.experience_levels, t)">{{ t }}</mat-checkbox>
            }
          </div>
        </div>
      </div>

      <div class="panel">
        <h2>Sites to search</h2>
        <div class="sites">
          @for (s of sites(); track s.key) {
            <mat-checkbox [checked]="p.sites.includes(s.key)" (change)="flip(p.sites, s.key)" [disabled]="!s.enabled">
              {{ s.name }}
              @if (!ready(s.key)) { <span class="phase">no scraper</span> }
              @if (!s.enabled) { <span class="phase">disabled</span> }
            </mat-checkbox>
          }
        </div>
        <p class="muted small">Add other sites or company career pages on <a routerLink="/sources">Companies &amp; Sites</a>.</p>
      </div>

      <div class="panel">
        <h2>Matching</h2>
        <div class="grid2">
          <mat-form-field>
            <mat-label>Base resume for this profile</mat-label>
            <mat-select [(ngModel)]="p.resume_id">
              @for (r of resumes(); track r.id) { <mat-option [value]="r.id">{{ r.name }}{{ r.is_default ? ' (default)' : '' }}</mat-option> }
            </mat-select>
            @if (!resumes().length) { <mat-hint>Upload a resume on the Resumes page first</mat-hint> }
          </mat-form-field>
          <mat-form-field>
            <mat-label>Max new jobs per run</mat-label>
            <input matInput type="number" min="1" max="200" [(ngModel)]="p.max_jobs" />
          </mat-form-field>
          <mat-form-field>
            <mat-label>Skip jobs asking for more than (years)</mat-label>
            <input matInput type="number" min="0" max="30" [(ngModel)]="p.max_years" />
            <mat-hint>0 = no limit. New grads: 2–3 keeps "8+ years" roles out</mat-hint>
          </mat-form-field>
        </div>
        <div class="label">Minimum match score to tailor a resume: <b>{{ p.min_score }}</b></div>
        <mat-slider min="0" max="100" step="5" discrete class="full">
          <input matSliderThumb [(ngModel)]="p.min_score" />
        </mat-slider>
      </div>

      <div class="actions sticky">
        <button mat-flat-button (click)="save(false)"><mat-icon>save</mat-icon> Save</button>
        <button mat-stroked-button (click)="save(true)" [disabled]="api.activeRuns().length > 0">
          <mat-icon>play_arrow</mat-icon> Save &amp; run now
        </button>
        <a mat-button routerLink="/profiles">Cancel</a>
      </div>
    }
  `,
  styles: `
    .label { font-weight: 500; margin: 6px 0 6px; }
    .suggest-row { margin-bottom: 10px; }
    mat-checkbox { margin-right: 14px; }
    .mode { margin: -4px 0 14px; }
    .sites { display: flex; flex-wrap: wrap; gap: 4px 8px; }
    .sticky { position: sticky; bottom: 0; padding: 12px 0; background: var(--bg); }
  `,
})
export class ProfileEditPage {
  protected api = inject(Api);
  private router = inject(Router);
  private dialog = inject(MatDialog);
  /** Route param: a profile id, or "new". */
  id = input.required<string>();
  protected p = signal<Profile | null>(null);
  protected sites = signal<Site[]>([]);
  protected resumes = signal<Resume[]>([]);
  protected meta = this.api.meta;
  protected isNew = () => this.id() === 'new';

  ngOnInit() {
    this.init();
  }

  private async init() {
    const [sites, resumes] = await Promise.all([this.api.get<Site[]>('/sites'), this.api.get<Resume[]>('/resumes')]);
    this.sites.set(sites);
    this.resumes.set(resumes);
    if (this.isNew()) {
      const def = resumes.find((r) => r.is_default) ?? resumes[0];
      this.p.set(structuredClone({ ...BLANK, resume_id: def?.id ?? null }));
    } else {
      this.p.set(await this.api.get<Profile>(`/profiles/${this.id()}`));
    }
  }

  suggest() {
    const p = this.p()!;
    const ref = this.dialog.open<SuggestDialog, unknown, SuggestResult>(SuggestDialog, {
      data: { resumeId: p.resume_id, profileId: p.id ?? null, inEditor: true }, width: '760px', maxWidth: '95vw', autoFocus: false,
    });
    ref.afterClosed().subscribe((res) => {
      if (!res) return;
      this.p.set({
        ...p,
        keywords: mergeList(p.keywords, res.keywords),
        exclude: mergeList(p.exclude, res.exclude),
        must_include: mergeList(p.must_include, res.must_include),
        ...(res.max_years !== null ? { max_years: res.max_years, experience_levels: res.experience_levels ?? p.experience_levels } : {}),
      });
      this.api.toast('Added to the form. Review, then press Save.');
    });
  }

  ready(key: string) {
    return this.meta()?.implemented_sites.includes(key) ?? false;
  }

  flip(list: string[], v: string) {
    const i = list.indexOf(v);
    if (i >= 0) list.splice(i, 1);
    else list.push(v);
  }

  async save(andRun: boolean) {
    const p = this.p()!;
    if (!p.name.trim()) return this.api.toast('Give the profile a name', true);
    if (!p.keywords.length) return this.api.toast('Add at least one search keyword', true);
    const saved = this.isNew()
      ? await this.api.post<Profile>('/profiles', p)
      : await this.api.put<Profile>(`/profiles/${p.id}`, p);
    this.api.toast('Saved');
    if (andRun) {
      await this.api.post(`/profiles/${saved.id}/run`);
      this.api.toast(`Running "${saved.name}". A browser window will open.`);
      this.api.refreshRuns();
    }
    this.router.navigate(['/profiles']);
  }
}

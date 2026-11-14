import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatRadioModule } from '@angular/material/radio';
import { MatSelectModule } from '@angular/material/select';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Api, Profile, SuggestItem, Suggestions } from '../api';

export interface SuggestDialogData {
  resumeId: number;
  /** When opened from the profile editor: suggestions skip what the profile already has, and no target choice is shown. */
  profileId?: number | null;
  inEditor?: boolean;
}

export interface SuggestResult {
  keywords: string[];
  exclude: string[];
  must_include: string[];
  max_years: number | null;
  experience_levels: string[] | null;
  target: { kind: 'new'; name: string } | { kind: 'existing'; id: number } | { kind: 'editor' };
}

@Component({
  selector: 'app-suggest-dialog',
  imports: [FormsModule, MatDialogModule, MatButtonModule, MatCheckboxModule, MatFormFieldModule, MatInputModule,
    MatRadioModule, MatSelectModule, MatProgressBarModule],
  template: `
    <h2 mat-dialog-title>Suggestions from your resume</h2>
    <mat-dialog-content>
      @if (!s()) {
        <p class="muted">Reading your resume…</p>
        <mat-progress-bar mode="indeterminate" />
      } @else {
        @let d = s()!;
        <p class="muted small">Resume: <b>{{ d.resume.name }}</b>. Tick what you want, untick what you don't.</p>

        @if (d.experience.years !== null) {
          <div class="note">
            Your work history adds up to about <b>{{ d.experience.years }} years</b>
            @if (d.experience.includes_internships) { (internships included) }.
            @if (d.experience.settings_years !== null && d.experience.settings_years !== d.experience.years) {
              Settings currently says {{ d.experience.settings_years }}.
              <button mat-button (click)="useYears(d.experience.years!)">Use {{ d.experience.years }} in Settings</button>
            }
          </div>
        }

        <h3>Roles you fit</h3>
        <div>
          @for (r of d.roles; track r.name) {
            @if (r.confidence >= 0.2) {
              <span class="tag" [class.good]="r.confidence >= 0.5" [title]="'Shows: ' + r.matched.join(', ')">
                {{ r.name }} · {{ (r.confidence * 100).toFixed(0) }}%
              </span>
            }
          }
        </div>

        <h3>Your strongest skills</h3>
        <div>@for (k of d.skills.slice(0, 15); track k.name) { <span class="tag info">{{ k.name }}</span> }</div>

        <h3>Job titles to search <span class="muted small">({{ count(d.suggestions.keywords) }} ticked; 4–6 works best)</span></h3>
        @for (k of d.suggestions.keywords; track k.value; let i = $index) {
          @if (i === 0 || group(k.reason) !== group(d.suggestions.keywords[i - 1].reason)) {
            <div class="group muted small">{{ group(k.reason) }}</div>
          }
          <div class="item"><mat-checkbox [(ngModel)]="k.selected">{{ k.value }}</mat-checkbox></div>
        } @empty { <p class="muted">No new titles to suggest.</p> }

        @if (d.suggestions.exclude.length) {
          <h3>Words to exclude from job titles</h3>
          <div class="row">
            @for (k of d.suggestions.exclude; track k.value) { <mat-checkbox [(ngModel)]="k.selected">{{ k.value }}</mat-checkbox> }
          </div>
          <p class="muted small">{{ d.suggestions.exclude[0].reason }}</p>
        }

        @if (d.suggestions.must_include.length) {
          <h3>Must include (optional)</h3>
          @for (k of d.suggestions.must_include; track k.value) {
            <div class="item"><mat-checkbox [(ngModel)]="k.selected">{{ k.value }}</mat-checkbox>
              <span class="muted small">{{ k.reason }}</span></div>
          }
        }

        <h3>Profile settings</h3>
        <div class="row">
          <mat-checkbox [(ngModel)]="applyLimits">
            Skip jobs asking more than <b>{{ d.profile_defaults.max_years }}</b> years; levels: {{ d.profile_defaults.experience_levels.join(', ') }}
          </mat-checkbox>
        </div>

        @if (!data.inEditor) {
          <h3>Where to put them</h3>
          <mat-radio-group [(ngModel)]="targetKind" class="targets">
            <mat-radio-button value="new">Create a new profile named</mat-radio-button>
            <mat-form-field subscriptSizing="dynamic" class="name"><input matInput [(ngModel)]="newName" /></mat-form-field>
            @if (profiles().length) {
              <mat-radio-button value="existing">Add to profile</mat-radio-button>
              <mat-form-field subscriptSizing="dynamic" class="name">
                <mat-select [(ngModel)]="existingId" (selectionChange)="targetKind = 'existing'">
                  @for (p of profiles(); track p.id) { <mat-option [value]="p.id">{{ p.name }}</mat-option> }
                </mat-select>
              </mat-form-field>
            }
          </mat-radio-group>
        }
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-flat-button [disabled]="!s() || !canApply()" (click)="apply()">
        {{ data.inEditor ? 'Add to this profile' : targetKind === 'new' ? 'Create profile' : 'Add to profile' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: `
    h3 { font-size: 13px; font-weight: 600; margin: 16px 0 6px; }
    .item { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin-left: 8px; }
    .group { margin: 10px 0 2px; }
    .note { background: var(--accent-soft); border-radius: 8px; padding: 8px 12px; font-size: 13px; }
    .targets { display: grid; grid-template-columns: auto 1fr; gap: 8px 12px; align-items: center; }
    .name { width: 280px; }
  `,
})
export class SuggestDialog {
  protected data = inject<SuggestDialogData>(MAT_DIALOG_DATA);
  private ref = inject(MatDialogRef<SuggestDialog, SuggestResult>);
  private api = inject(Api);
  protected s = signal<Suggestions | null>(null);
  protected profiles = signal<Profile[]>([]);
  protected applyLimits = true;
  protected targetKind: 'new' | 'existing' = 'new';
  protected newName = '';
  protected existingId: number | null = null;

  constructor() {
    this.load();
  }

  private async load() {
    try {
      const [s, profiles] = await Promise.all([
        this.api.get<Suggestions>(`/resumes/${this.data.resumeId}/suggestions`, { profile_id: this.data.profileId }),
        this.data.inEditor ? Promise.resolve([] as Profile[]) : this.api.get<Profile[]>('/profiles'),
      ]);
      this.newName = s.profile_defaults.name;
      this.profiles.set(profiles);
      this.s.set(s);
    } catch {
      this.ref.close();
    }
  }

  /** Group label for a title: the reason without the "(entry-level title)" note. */
  group(reason: string) {
    return reason.replace(/\s*\(entry-level title\)$/, '');
  }

  count(items: SuggestItem[]) {
    return items.filter((i) => i.selected).length;
  }

  canApply() {
    if (this.data.inEditor) return true;
    if (this.targetKind === 'existing') return !!this.existingId;
    return !!this.newName.trim();
  }

  async useYears(years: number) {
    await this.api.put('/settings', { years_of_experience: years });
    this.s.update((d) => (d ? { ...d, experience: { ...d.experience, settings_years: years } } : d));
    this.api.toast(`Settings updated: ${years} years of experience`);
  }

  apply() {
    const d = this.s()!;
    const pick = (xs: SuggestItem[]) => xs.filter((x) => x.selected).map((x) => x.value);
    this.ref.close({
      keywords: pick(d.suggestions.keywords),
      exclude: pick(d.suggestions.exclude),
      must_include: pick(d.suggestions.must_include),
      max_years: this.applyLimits ? d.profile_defaults.max_years : null,
      experience_levels: this.applyLimits ? d.profile_defaults.experience_levels : null,
      target: this.data.inEditor ? { kind: 'editor' }
        : this.targetKind === 'new' ? { kind: 'new', name: this.newName.trim() } : { kind: 'existing', id: this.existingId! },
    });
  }
}

/** Merge lists without duplicates (case-insensitive), keeping existing order first. */
export function mergeList(existing: string[], add: string[]): string[] {
  const seen = new Set(existing.map((x) => x.toLowerCase()));
  return [...existing, ...add.filter((x) => !seen.has(x.toLowerCase()) && seen.add(x.toLowerCase()))];
}

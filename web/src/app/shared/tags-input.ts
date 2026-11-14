import { Component, input, model } from '@angular/core';
import { COMMA, ENTER } from '@angular/cdk/keycodes';
import { MatChipInputEvent, MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';

/** Tag editor: type and press Enter or comma; paste "a, b, c" to add several. */
@Component({
  selector: 'app-tags-input',
  imports: [MatChipsModule, MatFormFieldModule, MatIconModule],
  template: `
    <mat-form-field class="full" subscriptSizing="dynamic">
      <mat-label>{{ label() }}</mat-label>
      <mat-chip-grid #grid [attr.aria-label]="label()">
        @for (t of value(); track t) {
          <mat-chip-row (removed)="remove(t)" [class]="tone()">
            {{ t }}
            <button matChipRemove [attr.aria-label]="'remove ' + t"><mat-icon>cancel</mat-icon></button>
          </mat-chip-row>
        }
        <input [placeholder]="placeholder()" [matChipInputFor]="grid"
          [matChipInputSeparatorKeyCodes]="splitOnComma() ? withComma : enterOnly" [matChipInputAddOnBlur]="true"
          (matChipInputTokenEnd)="add($event)" />
      </mat-chip-grid>
      @if (hint()) { <mat-hint>{{ hint() }}</mat-hint> }
    </mat-form-field>
  `,
  styles: `
    :host { display: block; margin-bottom: 14px; }
    mat-chip-row.exclude { --mat-chip-elevated-container-color: var(--bad-soft); }
    mat-chip-row.must { --mat-chip-elevated-container-color: var(--good-soft); }
  `,
})
export class TagsInput {
  label = input('');
  placeholder = input('Type and press Enter');
  hint = input('');
  tone = input<'' | 'exclude' | 'must'>('');
  /** Off for values that contain commas themselves, like "Dallas, TX". */
  splitOnComma = input(true);
  value = model<string[]>([]);
  protected withComma = [ENTER, COMMA] as const;
  protected enterOnly = [ENTER] as const;

  add(e: MatChipInputEvent) {
    const raw = e.value || '';
    const parts = (this.splitOnComma() ? raw.split(',') : [raw]).map((s) => s.trim()).filter(Boolean);
    if (parts.length) {
      const cur = this.value();
      const lower = new Set(cur.map((c) => c.toLowerCase()));
      const next = [...cur];
      for (const p of parts) if (!lower.has(p.toLowerCase())) { next.push(p); lower.add(p.toLowerCase()); }
      this.value.set(next);
    }
    e.chipInput.clear();
  }

  remove(t: string) {
    this.value.set(this.value().filter((x) => x !== t));
  }
}

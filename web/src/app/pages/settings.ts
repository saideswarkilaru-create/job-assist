import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { Api, SettingSpec } from '../api';
import { SchedulePanel } from '../shared/schedule-panel';

@Component({
  selector: 'app-settings',
  imports: [SchedulePanel, FormsModule, MatButtonModule, MatFormFieldModule, MatIconModule, MatInputModule, MatSelectModule, MatSlideToggleModule],
  template: `
    <div class="page-head">
      <div class="grow">
        <h1>Settings</h1>
        <p class="sub">Pacing, AI models, limits and schedule. Low, human-paced volume keeps your accounts safe.</p>
      </div>
      <button mat-flat-button (click)="save()"><mat-icon>save</mat-icon> Save settings</button>
    </div>
    <app-schedule-panel />
    @for (g of groups(); track g.name) {
      <div class="panel">
        <h2>{{ g.name }}</h2>
        @for (s of g.items; track s.key) {
          <div class="setting">
            @switch (s.type) {
              @case ('bool') {
                <mat-slide-toggle [(ngModel)]="values[s.key]">{{ s.label }}</mat-slide-toggle>
              }
              @case ('select') {
                <mat-form-field subscriptSizing="dynamic" class="f">
                  <mat-label>{{ s.label }}</mat-label>
                  <mat-select [(ngModel)]="values[s.key]">
                    @for (o of s.options; track o) { <mat-option [value]="o">{{ o }}</mat-option> }
                  </mat-select>
                </mat-form-field>
              }
              @case ('textarea') {
                <mat-form-field subscriptSizing="dynamic" class="f wide">
                  <mat-label>{{ s.label }}</mat-label>
                  <textarea matInput rows="5" [(ngModel)]="values[s.key]"></textarea>
                </mat-form-field>
              }
              @case ('text') {
                <mat-form-field subscriptSizing="dynamic" class="f">
                  <mat-label>{{ s.label }}</mat-label>
                  <input matInput [(ngModel)]="values[s.key]" />
                  @if (s.key === 'tailored_file_pattern') {
                    <mat-hint>Example: <b>{{ example(values[s.key]) }}.pdf</b></mat-hint>
                  }
                </mat-form-field>
              }
              @case ('time') {
                <mat-form-field subscriptSizing="dynamic" class="f">
                  <mat-label>{{ s.label }}</mat-label>
                  <input matInput type="time" [(ngModel)]="values[s.key]" />
                </mat-form-field>
              }
              @default {
                <mat-form-field subscriptSizing="dynamic" class="f">
                  <mat-label>{{ s.label }}</mat-label>
                  <input matInput type="number" [min]="s.min ?? null" [max]="s.max ?? null" [(ngModel)]="values[s.key]" />
                </mat-form-field>
              }
            }
            @if (s.phase) { <span class="phase">used from Phase {{ s.phase }}</span> }
          </div>
        }
      </div>
    }
  `,
  styles: `
    .setting { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
    .f { width: 460px; max-width: 100%; }
    .f.wide { width: 720px; }
  `,
})
export class SettingsPage {
  private api = inject(Api);
  private spec = signal<SettingSpec[]>([]);
  protected values: Record<string, any> = {};
  protected groups = computed(() => {
    const out: { name: string; items: SettingSpec[] }[] = [];
    for (const s of this.spec()) {
      let g = out.find((x) => x.name === s.group);
      if (!g) out.push((g = { name: s.group, items: [] }));
      g.items.push(s);
    }
    return out;
  });

  constructor() {
    this.load();
  }

  async load() {
    const r = await this.api.get<{ spec: SettingSpec[]; values: Record<string, any> }>('/settings');
    this.values = { ...r.values };
    this.spec.set(r.spec);
  }

  /** Same rules as the server: placeholders filled, unsafe characters become _. */
  example(pattern: string) {
    const name = (this.values['full_name'] || 'Priya Sample').trim();
    const vals: Record<string, string> = {
      name: name.replace(/[^A-Za-z0-9]+/g, '_'), role: 'Java_Developer', company: 'Acme',
      date: new Date().toISOString().slice(0, 10),
    };
    let out = pattern || '{name}_{role}_Resume';
    for (const [k, v] of Object.entries(vals)) out = out.split('{' + k + '}').join(v);
    return out.replace(/[^A-Za-z0-9._ -]+/g, '_').replace(/_+/g, '_').replace(/^[_. -]+|[_. -]+$/g, '') || 'Resume';
  }

  async save() {
    const r = await this.api.put<{ values: Record<string, any> }>('/settings', this.values);
    this.values = { ...r.values };
    this.api.toast('Settings saved');
  }
}

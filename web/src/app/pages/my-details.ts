import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { Api } from '../api';

interface Field { key: string; label: string; group: string; type?: 'select'; options?: string[]; help?: string; }
interface QA { question: string; answer: string; }

@Component({
  selector: 'app-my-details',
  imports: [FormsModule, MatButtonModule, MatFormFieldModule, MatIconModule, MatInputModule, MatSelectModule],
  template: `
    <div class="page-head">
      <div class="grow">
        <h1>My details</h1>
        <p class="sub">What the app types into application forms for you. Stored only on this computer
          (<code>config\\profile.yaml</code>). Never put passwords here. Questions the app can't answer honestly are left for you.</p>
      </div>
      <button mat-flat-button (click)="save()"><mat-icon>save</mat-icon> Save</button>
    </div>

    @for (g of groups(); track g.name) {
      <div class="panel">
        <h2>{{ g.name }}</h2>
        @if (g.name.startsWith('Voluntary')) {
          <p class="muted small">US employers must ask these, but answering is optional and never affects hiring decisions by law.
            "Decline to answer" is always fine.</p>
        }
        <div class="grid2">
          @for (f of g.items; track f.key) {
            <mat-form-field subscriptSizing="dynamic" class="f">
              <mat-label>{{ f.label }}</mat-label>
              @if (f.type === 'select') {
                <mat-select [(ngModel)]="values[f.key]">
                  @for (o of f.options; track o) { <mat-option [value]="o">{{ o || '(not set)' }}</mat-option> }
                </mat-select>
              } @else {
                <input matInput [(ngModel)]="values[f.key]" />
              }
              @if (f.help) { <mat-hint>{{ f.help }}</mat-hint> }
            </mat-form-field>
          }
        </div>
      </div>
    }

    <div class="panel">
      <h2>My answers to common questions</h2>
      <p class="muted small">When a form asks a question containing these words, the app uses your answer.
        For example: <i>notice period</i> → <i>2 weeks</i>, <i>why do you want to work</i> → your short paragraph.</p>
      @for (qa of answers(); track $index; let i = $index) {
        <div class="row qa">
          <mat-form-field subscriptSizing="dynamic" class="q"><mat-label>If the question mentions</mat-label>
            <input matInput [(ngModel)]="qa.question" /></mat-form-field>
          <mat-form-field subscriptSizing="dynamic" class="a"><mat-label>Answer</mat-label>
            <textarea matInput rows="1" [(ngModel)]="qa.answer"></textarea></mat-form-field>
          <button mat-icon-button (click)="remove(i)"><mat-icon>delete</mat-icon></button>
        </div>
      }
      <button mat-stroked-button (click)="add()"><mat-icon>add</mat-icon> Add an answer</button>
    </div>
    <div class="actions"><button mat-flat-button (click)="save()"><mat-icon>save</mat-icon> Save</button></div>
  `,
  styles: `
    .f { width: 100%; margin-bottom: 14px; }
    .qa { flex-wrap: nowrap; margin-bottom: 8px; } .q { width: 260px; } .a { flex: 1; }
    code { font-size: 12px; }
  `,
})
export class MyDetailsPage {
  private api = inject(Api);
  private spec = signal<Field[]>([]);
  protected values: Record<string, any> = {};
  protected answers = signal<QA[]>([]);
  protected groups = computed(() => {
    const out: { name: string; items: Field[] }[] = [];
    for (const f of this.spec()) {
      let g = out.find((x) => x.name === f.group);
      if (!g) out.push((g = { name: f.group, items: [] }));
      g.items.push(f);
    }
    return out;
  });

  constructor() {
    this.load();
  }

  async load() {
    const r = await this.api.get<{ spec: Field[]; values: Record<string, any> }>('/applicant');
    this.values = { ...r.values };
    this.answers.set((r.values['answers'] ?? []).map((a: QA) => ({ ...a })));
    this.spec.set(r.spec);
  }

  add() {
    this.answers.update((a) => [...a, { question: '', answer: '' }]);
  }

  remove(i: number) {
    this.answers.update((a) => a.filter((_, j) => j !== i));
  }

  async save() {
    const r = await this.api.put<{ values: Record<string, any> }>('/applicant', { ...this.values, answers: this.answers() });
    this.values = { ...r.values };
    this.answers.set((r.values['answers'] ?? []).map((a: QA) => ({ ...a })));
    this.api.toast('Saved. These details are used only to fill your applications.');
  }
}

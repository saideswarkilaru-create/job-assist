import { Component, DestroyRef, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api, Company, Login, Site } from '../api';

interface LoginEdit extends Login { password: string; dirty: boolean; }

@Component({
  selector: 'app-sources',
  imports: [DatePipe, FormsModule, MatButtonModule, MatButtonToggleModule, MatFormFieldModule, MatIconModule,
    MatInputModule, MatSelectModule, MatSlideToggleModule, MatTooltipModule],
  template: `
    <div class="page-head"><div class="grow">
      <h1>Companies &amp; Sites</h1>
      <p class="sub">Where your profiles search, and how you sign in to each place.</p>
    </div></div>

    <!-- ============ Job sites ============ -->
    <div class="panel">
      <h2>Job sites</h2>
      <div class="table-wrap">
        <table class="data">
          <thead><tr><th>On</th><th>Site</th><th>Type</th><th>Status</th><th>Search URL / notes</th><th></th></tr></thead>
          <tbody>
            @for (s of sites(); track s.id) {
              <tr>
                <td><mat-slide-toggle [checked]="s.enabled" (change)="toggleSite(s, $event.checked)" /></td>
                <td><b>{{ s.name }}</b></td>
                <td class="small">{{ s.kind }}</td>
                <td>@if (ready(s)) { <span class="tag good">ready</span> } @else { <span class="tag">no scraper</span> }</td>
                <td class="small">{{ s.search_url || s.notes }}</td>
                <td>@if (s.kind === 'custom') { <button mat-icon-button (click)="removeSite(s)" matTooltip="Delete"><mat-icon>delete</mat-icon></button> }</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
      <h2 class="sub-h">Add another job site</h2>
      <div class="row">
        <mat-form-field subscriptSizing="dynamic"><mat-label>Name</mat-label><input matInput [(ngModel)]="site.name" placeholder="e.g. Monster" /></mat-form-field>
        <mat-form-field subscriptSizing="dynamic" class="wide">
          <mat-label>Search URL</mat-label>
          <input matInput [(ngModel)]="site.search_url" placeholder="https://www.example.com/jobs?q={keyword}&l={location}" />
          <mat-hint>Search the site once, copy the address, and replace your words with {{ '{' }}keyword{{ '}' }} and {{ '{' }}location{{ '}' }}</mat-hint>
        </mat-form-field>
        <button mat-flat-button (click)="addSite()"><mat-icon>add</mat-icon> Add site</button>
      </div>
    </div>

    <!-- ============ Companies ============ -->
    <div class="panel">
      <h2>Company career pages</h2>
      <p class="muted small">Searched when a profile ticks "Company career pages". Press <b>Test</b> to check a company with one keyword (nothing is saved).</p>
      <div class="table-wrap">
        <table class="data">
          <thead><tr><th>On</th><th>Company</th><th>Careers URL</th><th>Handler</th><th>Last check</th><th></th></tr></thead>
          <tbody>
            @for (c of companies(); track c.id) {
              <tr>
                <td><mat-slide-toggle [checked]="c.enabled" (change)="toggleCompany(c, $event.checked)" /></td>
                <td><b>{{ c.name }}</b></td>
                <td class="small url"><a [href]="c.careers_url" target="_blank" rel="noopener">{{ c.careers_url }}</a></td>
                <td>
                  <mat-select class="adapter" [value]="c.adapter || ''" (selectionChange)="setAdapter(c, $event.value)">
                    <mat-option value="">automatic</mat-option>
                    @for (a of adapters(); track a) { <mat-option [value]="a">{{ a }}</mat-option> }
                  </mat-select>
                </td>
                <td class="small">
                  @if (c.last_status) {
                    <span [class]="c.last_status.startsWith('ok') ? 'tag good' : 'tag warn'">{{ c.last_status }}</span>
                    <div class="muted">{{ c.last_checked_at + 'Z' | date: 'MMM d, h:mm a' }}</div>
                  } @else { <span class="muted">not checked yet</span> }
                </td>
                <td class="nowrap">
                  <button mat-stroked-button (click)="test(c)" [disabled]="api.activeRuns().length > 0">Test</button>
                  <button mat-icon-button (click)="removeCompany(c)" matTooltip="Delete"><mat-icon>delete</mat-icon></button>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>
      <h2 class="sub-h">Add a company</h2>
      <div class="row">
        <mat-form-field subscriptSizing="dynamic"><mat-label>Company</mat-label><input matInput [(ngModel)]="company.name" placeholder="e.g. Infosys" /></mat-form-field>
        <mat-form-field subscriptSizing="dynamic" class="wide"><mat-label>Careers page URL</mat-label><input matInput [(ngModel)]="company.careers_url" placeholder="https://..." /></mat-form-field>
        <button mat-flat-button (click)="addCompany()"><mat-icon>add</mat-icon> Add company</button>
      </div>
    </div>

    <!-- ============ Logins ============ -->
    <div class="panel">
      <h2>Sign-in</h2>
      <p class="muted small">
        <b>I'll log in myself</b> (recommended): press <i>Log in now</i>, sign in in the window that opens, close it. You stay signed in.<br />
        <b>Save my login</b>: the app signs in for you when a site asks. Your password is stored only in
        <b>Windows Credential Manager</b> (encrypted by Windows), never in the app's files. Two-step codes and captchas still come to you.
      </p>
      <div class="logins">
        @for (l of logins(); track l.login_key) {
          <div class="login-row">
            <div class="who"><b>{{ l.name }}</b>
              @if (l.mode === 'saved' && l.password_saved && !l.dirty) { <span class="tag good">login saved</span> }
            </div>
            <mat-button-toggle-group [(ngModel)]="l.mode" (change)="l.dirty = true" class="mode">
              <mat-button-toggle value="manual">I'll log in myself</mat-button-toggle>
              <mat-button-toggle value="saved">Save my login</mat-button-toggle>
            </mat-button-toggle-group>
            @if (l.mode === 'saved') {
              <mat-form-field subscriptSizing="dynamic" class="cred">
                <mat-label>Email / username</mat-label>
                <input matInput [(ngModel)]="l.username" (input)="l.dirty = true" autocomplete="off" />
              </mat-form-field>
              <mat-form-field subscriptSizing="dynamic" class="cred">
                <mat-label>{{ l.password_saved ? 'Password (saved, type to change)' : 'Password' }}</mat-label>
                <input matInput type="password" [(ngModel)]="l.password" (input)="l.dirty = true" autocomplete="new-password" />
              </mat-form-field>
            }
            @if (l.dirty) { <button mat-flat-button (click)="saveLogin(l)">Save</button> }
            <button mat-stroked-button (click)="loginNow(l)" [disabled]="api.activeRuns().length > 0">
              <mat-icon>login</mat-icon> Log in now
            </button>
          </div>
        }
      </div>
    </div>
  `,
  styles: `
    .wide { width: 460px; max-width: 100%; }
    .sub-h { margin-top: 18px; }
    .url { max-width: 320px; word-break: break-all; }
    .adapter { width: 140px; }
    .nowrap { white-space: nowrap; }
    .logins { display: flex; flex-direction: column; gap: 10px; }
    .login-row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--line); }
    .who { width: 200px; }
    .cred { width: 230px; }
  `,
})
export class SourcesPage {
  protected api = inject(Api);
  protected sites = signal<Site[]>([]);
  protected companies = signal<Company[]>([]);
  protected logins = signal<LoginEdit[]>([]);
  protected adapters = signal<string[]>([]);
  protected site = { name: '', search_url: '' };
  protected company = { name: '', careers_url: '' };

  constructor() {
    this.load();
    // refresh company status after a Test run finishes
    let busy = false;
    const t = setInterval(() => {
      const now = this.api.activeRuns().length > 0;
      if (busy && !now) this.loadCompanies();
      busy = now;
    }, 2000);
    inject(DestroyRef).onDestroy(() => clearInterval(t));
  }

  async load() {
    const [s, a, l] = await Promise.all([
      this.api.get<Site[]>('/sites'), this.api.get<string[]>('/adapters'), this.api.get<Login[]>('/logins'),
    ]);
    this.sites.set(s);
    this.adapters.set(a);
    this.logins.set(l.map((x) => ({ ...x, password: '', dirty: false })));
    await this.loadCompanies();
  }

  async loadCompanies() {
    this.companies.set(await this.api.get<Company[]>('/companies'));
  }

  ready(s: Site) {
    return s.kind === 'custom' || (this.api.meta()?.implemented_sites.includes(s.key) ?? false);
  }

  async toggleSite(s: Site, enabled: boolean) {
    await this.api.put(`/sites/${s.id}`, { enabled });
    this.load();
  }

  async addSite() {
    await this.api.post('/sites', this.site);
    this.site = { name: '', search_url: '' };
    this.load();
  }

  async removeSite(s: Site) {
    if (!confirm(`Delete site "${s.name}"?`)) return;
    await this.api.delete(`/sites/${s.id}`);
    this.load();
  }

  async toggleCompany(c: Company, enabled: boolean) {
    await this.api.put(`/companies/${c.id}`, { enabled });
    this.loadCompanies();
  }

  async setAdapter(c: Company, adapter: string) {
    await this.api.put(`/companies/${c.id}`, { adapter: adapter || null });
    this.loadCompanies();
  }

  async addCompany() {
    await this.api.post('/companies', this.company);
    this.company = { name: '', careers_url: '' };
    this.load();
  }

  async removeCompany(c: Company) {
    if (!confirm(`Delete "${c.name}"?`)) return;
    await this.api.delete(`/companies/${c.id}`);
    this.load();
  }

  async test(c: Company) {
    const keyword = prompt(`Test ${c.name} with which keyword?`, 'Java developer');
    if (keyword === null) return;
    await this.api.post(`/companies/${c.id}/test`, { keyword });
    this.api.toast(`Testing ${c.name}… watch the browser window. The result shows here and on Runs & logs.`);
    this.api.refreshRuns();
  }

  async saveLogin(l: LoginEdit) {
    await this.api.put(`/logins/${l.login_key}`, { mode: l.mode, username: l.username, password: l.password });
    this.api.toast(l.mode === 'saved' ? `Login for ${l.name} saved in Windows Credential Manager` : `${l.name}: you'll log in yourself`);
    const fresh = await this.api.get<Login[]>('/logins');
    this.logins.set(fresh.map((x) => ({ ...x, password: '', dirty: false })));
  }

  async loginNow(l: LoginEdit) {
    await this.api.post('/runs/login', { login_key: l.login_key });
    this.api.toast(`Opening ${l.name}. Sign in if asked, then close the browser window.`);
    this.api.refreshRuns();
  }
}

import { Component, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api } from '../api';

interface Row { name: string; found: number; matched: number; applied: number; responses: number; interviews: number;
  offers: number; response_rate: number | null; interview_rate: number | null; avg_score?: number | null; }
interface Stats {
  summary: { applied: number; responses: number; interviews: number; response_rate: number | null; interview_rate: number | null;
             applied_today: number; daily_cap: number; follow_up_due: number; applied_7d: number };
  funnel: { step: string; count: number }[];
  profiles: Row[]; sites: Row[]; keywords: Row[];
  hidden: { reason: string; count: number }[];
  weekly: { week: string; start: string; applied: number }[];
  scores: { applied: number | null; interviewed: number | null; no_response: number | null };
}

@Component({
  selector: 'app-stats',
  imports: [DatePipe, DecimalPipe, MatTooltipModule],
  template: `
    <div class="page-head"><div class="grow">
      <h1>Stats</h1>
      <p class="sub">What's working: which profiles, sites and search words lead to replies and interviews.</p>
    </div></div>

    @if (s(); as s) {
      <div class="tiles">
        <div class="tile"><div class="k">Applied, last 7 days</div><div class="v">{{ s.summary.applied_7d }}</div>
          <div class="muted small">{{ s.summary.applied }} in total</div></div>
        <div class="tile"><div class="k">Response rate</div><div class="v">{{ pct(s.summary.response_rate) }}</div>
          <div class="muted small">{{ s.summary.responses }} of {{ s.summary.applied }} replied</div></div>
        <div class="tile"><div class="k">Interview rate</div><div class="v">{{ pct(s.summary.interview_rate) }}</div>
          <div class="muted small">{{ s.summary.interviews }} interview(s)</div></div>
        <div class="tile"><div class="k">Today</div><div class="v">{{ s.summary.applied_today }}<span class="of"> / {{ s.summary.daily_cap }}</span></div>
          <div class="muted small">daily limit</div></div>
        <div class="tile" [class.warn]="s.summary.follow_up_due"><div class="k">Follow-ups due</div><div class="v">{{ s.summary.follow_up_due }}</div>
          <div class="muted small"><a href="/applications">open Applications</a></div></div>
      </div>
      @if (s.summary.applied < 10) {
        <p class="muted small note">With fewer than 10 applications, rates move a lot from one reply. Read them as early signals.</p>
      }

      <div class="grid2">
        <div class="panel">
          <h2>Your funnel</h2>
          @for (f of s.funnel; track f.step; let i = $index) {
            <div class="hrow" [matTooltip]="funnelTip(s, i)">
              <span class="lbl">{{ f.step }}</span>
              <span class="track"><span class="bar" [style.width.%]="share(f.count, s.funnel[0].count)"></span></span>
              <span class="num">{{ f.count | number }}</span>
            </div>
          }
        </div>
        <div class="panel">
          <h2>Why jobs were hidden</h2>
          @if (!s.hidden.length) { <p class="muted">Nothing hidden yet.</p> }
          @for (h of s.hidden; track h.reason) {
            <div class="hrow" [matTooltip]="h.count + ' job(s) hidden: ' + h.reason">
              <span class="lbl">{{ h.reason }}</span>
              <span class="track"><span class="bar" [style.width.%]="share(h.count, s.hidden[0].count)"></span></span>
              <span class="num">{{ h.count }}</span>
            </div>
          }
          <p class="muted small">Change these in Settings (visa, clearance) or in each profile (years, excluded words).</p>
        </div>
      </div>

      <div class="panel">
        <h2>Applications per week</h2>
        <div class="weeks">
          @for (w of s.weekly; track w.week; let i = $index) {
            <div class="wk" [matTooltip]="'Week of ' + (w.start | date: 'MMM d') + ': ' + w.applied + ' application(s)'">
              <span class="wnum">{{ w.applied || '' }}</span>
              <span class="col" [style.height.%]="share(w.applied, maxWeek())"></span>
              <span class="wlbl">{{ i % 2 === 1 ? (w.start | date: 'MMM d') : '' }}</span>
            </div>
          }
        </div>
      </div>

      @for (t of tables(s); track t.title) {
        <div class="panel">
          <h2>{{ t.title }}</h2>
          @if (!t.rows.length) { <p class="muted">No data yet.</p> } @else {
            <div class="table-wrap">
              <table class="data">
                <thead><tr><th>{{ t.col }}</th><th class="n">Found</th><th class="n">Matched</th><th class="n">Applied</th>
                  <th class="n">Replies</th><th class="n">Interviews</th><th class="n">Reply rate</th><th class="n">Interview rate</th>
                  @if (t.score) { <th class="n">Avg score</th> }</tr></thead>
                <tbody>
                  @for (r of t.rows; track r.name) {
                    <tr><td>{{ r.name }}</td><td class="n">{{ r.found }}</td><td class="n">{{ r.matched }}</td><td class="n">{{ r.applied }}</td>
                      <td class="n">{{ r.responses }}</td><td class="n">{{ r.interviews }}</td>
                      <td class="n">{{ pct(r.response_rate) }}</td><td class="n">{{ pct(r.interview_rate) }}</td>
                      @if (t.score) { <td class="n">{{ r.avg_score ?? '–' }}</td> }</tr>
                  }
                </tbody>
              </table>
            </div>
          }
          <p class="muted small">{{ t.tip }}</p>
        </div>
      }

      @if (s.scores.applied !== null) {
        <div class="panel">
          <h2>Does the match score predict replies?</h2>
          <p>Average match score of jobs you applied to: <b>{{ s.scores.applied }}</b>
            @if (s.scores.interviewed !== null) { · that led to interviews: <b>{{ s.scores.interviewed }}</b> }
            @if (s.scores.no_response !== null) { · with no reply yet: <b>{{ s.scores.no_response }}</b> }</p>
          <p class="muted small">If interviews come from higher scores, raise the profile's minimum score and spend your time there.</p>
        </div>
      }
    }
  `,
  styles: `
    .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 8px; }
    .tile { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; }
    .tile.warn { background: var(--warn-soft); }
    .k { font-size: 12px; color: var(--muted); } .v { font-size: 28px; font-weight: 700; margin: 2px 0; } .of { font-size: 15px; color: var(--muted); }
    .note { margin: 0 0 14px; }
    .hrow { display: grid; grid-template-columns: 170px 1fr 48px; align-items: center; gap: 10px; padding: 5px 0; }
    .lbl { font-size: 13px; } .num { text-align: right; font-variant-numeric: tabular-nums; font-size: 13px; }
    .track { height: 14px; background: var(--hover); border-radius: 4px; overflow: hidden; }
    .bar { display: block; height: 100%; background: var(--accent); border-radius: 0 4px 4px 0; min-width: 2px; }
    .weeks { display: grid; grid-template-columns: repeat(12, 1fr); gap: 2px; height: 170px; align-items: end; border-bottom: 1px solid var(--line); }
    .wk { display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; position: relative; cursor: default; }
    .col { width: 60%; background: var(--accent); border-radius: 4px 4px 0 0; min-height: 0; }
    .wnum { font-size: 11px; color: var(--muted); margin-bottom: 2px; }
    .wlbl { position: absolute; bottom: -20px; font-size: 11px; color: var(--muted); white-space: nowrap; }
    .weeks + * { margin-top: 26px; }
    .panel:has(.weeks) { padding-bottom: 34px; }
    th.n, td.n { text-align: right; font-variant-numeric: tabular-nums; }
  `,
})
export class StatsPage {
  private api = inject(Api);
  protected s = signal<Stats | null>(null);
  protected maxWeek = computed(() => Math.max(1, ...(this.s()?.weekly ?? []).map((w) => w.applied)));

  constructor() {
    this.api.get<Stats>('/stats').then((s) => this.s.set(s));
  }

  pct(v: number | null) {
    return v === null || v === undefined ? '–' : `${v}%`;
  }

  share(n: number, max: number) {
    return max ? Math.max(0, (100 * n) / max) : 0;
  }

  funnelTip(s: Stats, i: number) {
    const f = s.funnel[i];
    if (i === 0) return `${f.count} unique jobs collected`;
    const prev = s.funnel[i - 1].count;
    return `${f.count} of ${prev} (${prev ? Math.round((100 * f.count) / prev) : 0}%) moved on from "${s.funnel[i - 1].step}"`;
  }

  tables(s: Stats) {
    return [
      { title: 'By profile', col: 'Profile', rows: s.profiles, score: false,
        tip: 'A profile with many matches but few replies may be searching the wrong titles. Try "Suggest keywords" on your resume.' },
      { title: 'By site', col: 'Site', rows: s.sites, score: false,
        tip: 'Spend your daily applications where replies come from.' },
      { title: 'By search word', col: 'Keyword', rows: s.keywords, score: true,
        tip: 'Keywords with matches but no interviews are candidates to drop; keep the ones that bring replies.' },
    ];
  }
}

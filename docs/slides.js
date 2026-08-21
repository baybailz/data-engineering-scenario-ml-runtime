/* Slides for this scenario. Each slide: {id, kicker, render() -> html}.
   S exposes shell helpers and the live data (S.D), config (S.CFG).
   Every number on these slides comes from docs/data/*.json. */
'use strict';
const m = t => `<span class="mono">${t}</span>`;
const n1 = v => v == null ? '—' : Number(v).toFixed(1);
const n2 = v => v == null ? '—' : Number(v).toFixed(2);

/* Predictions from the model that is currently published. The datamart has
   already restricted them to the latest version and joined the query shape. */
function latestPredictions() {
  return S.D.tables.dm_prediction_detail || [];
}
function gateBadge() {
  const s = S.D.summary || {};
  if (s.passes_gate == null) return S.badge('no model yet', 'b-dup');
  return s.passes_gate ? S.badge('GATE PASS', 'b-new', S.ICO.check)
                       : S.badge('GATE FAIL', 'b-dup');
}

/* Predicted against actual, both on log axes, with the 45 degree line.
   Drawn here from dm_prediction_detail rather than shipped as an image, so it
   cannot disagree with the table two tabs away. */
function scatterSvg() {
  const rows = latestPredictions().filter(r => r.actual_seconds > 0 && r.predicted_seconds > 0);
  if (!rows.length) return '<div class="empty">No predictions published yet.</div>';
  const W = 860, H = 400, L = 66, R = 20, T = 20, B = 44;
  const values = rows.flatMap(r => [r.actual_seconds, r.predicted_seconds]);
  const lo = Math.log10(Math.min(...values)) - 0.08, hi = Math.log10(Math.max(...values)) + 0.08;
  const x = v => L + (Math.log10(v) - lo) / (hi - lo) * (W - L - R);
  const y = v => H - B - (Math.log10(v) - lo) / (hi - lo) * (H - T - B);
  const ticks = [];
  for (let e = Math.ceil(lo); e <= Math.floor(hi); e++) ticks.push(Math.pow(10, e));
  const colour = ['var(--accent)', 'var(--good)', 'var(--warn)', 'var(--dup)'];
  const dots = rows.map(r => {
    const worst = r.abs_pct_error >= 30;
    return `<circle cx="${x(r.actual_seconds).toFixed(1)}" cy="${y(r.predicted_seconds).toFixed(1)}"
      r="${worst ? 5 : 3.6}" fill="${colour[Math.min(3, r.n_joins)]}"
      fill-opacity="${worst ? 0.95 : 0.6}" stroke="${worst ? 'var(--bad)' : 'none'}"
      stroke-width="1.6"><title>${S.esc(r.query_id)} · ${S.esc(r.template_label)}
actual ${Number(r.actual_seconds).toFixed(3)}s · predicted ${Number(r.predicted_seconds).toFixed(3)}s · ${n1(r.abs_pct_error)}%</title></circle>`;
  }).join('');
  const grid = ticks.map(t => `
    <line x1="${x(t)}" y1="${T}" x2="${x(t)}" y2="${H - B}" stroke="var(--border)" stroke-width="1"/>
    <line x1="${L}" y1="${y(t)}" x2="${W - R}" y2="${y(t)}" stroke="var(--border)" stroke-width="1"/>
    <text x="${x(t)}" y="${H - B + 18}" text-anchor="middle" font-size="11" fill="var(--ink3)">${t}s</text>
    <text x="${L - 10}" y="${y(t) + 4}" text-anchor="end" font-size="11" fill="var(--ink3)">${t}s</text>`).join('');
  const corner = Math.pow(10, lo), far = Math.pow(10, hi);
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Predicted against actual runtime">
    ${grid}
    <line x1="${x(corner)}" y1="${y(corner)}" x2="${x(far)}" y2="${y(far)}"
      stroke="var(--ink3)" stroke-width="1.4" stroke-dasharray="6 5"/>
    ${dots}
    <text x="${L + 8}" y="${T + 12}" font-size="11" fill="var(--ink3)">dashed line: a perfect prediction</text>
    <text x="${W - R}" y="${H - 6}" text-anchor="end" font-size="11.5" fill="var(--ink2)">measured seconds (log)</text>
    <text x="14" y="${T + 4}" font-size="11.5" fill="var(--ink2)" transform="rotate(-90 14 ${T + 4})" text-anchor="end">predicted seconds (log)</text>
  </svg>`;
}

/* Permutation importance, holdout, in log seconds. */
function importanceSvg() {
  const rows = (S.D.summary?.importances || []).filter(r => r.importance > 0).slice(0, 8);
  if (!rows.length) return '<div class="empty">No model published yet.</div>';
  const max = Math.max(...rows.map(r => r.importance));
  const W = 540, rowH = 46, H = rows.length * rowH + 14;
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;min-width:330px" role="img" aria-label="Feature importance">
    ${rows.map((r, i) => {
      const w = Math.max(2, r.importance / max * 300);
      return `<rect x="176" y="${i * rowH + 12}" width="${w}" height="20" rx="4"
          fill="${i === 0 ? 'var(--accent)' : 'var(--accent-2)'}" fill-opacity="${1 - i * 0.09}"/>
        <text x="166" y="${i * rowH + 27}" text-anchor="end" font-size="13"
          fill="var(--ink2)" font-family="ui-monospace,monospace">${S.esc(r.feature)}</text>
        <text x="${180 + w + 8}" y="${i * rowH + 27}" font-size="12.5" fill="var(--ink3)"
          font-variant-numeric="tabular-nums">${r.importance.toFixed(3)}</text>`;
    }).join('')}
  </svg>`;
}

/* The learning curve: holdout MAPE per model version as batches accumulate. */
function learningSvg() {
  const rows = (S.D.tables.dm_model_scorecard || []).slice();
  if (!rows.length) return '<div class="empty">No models trained yet.</div>';
  const W = 560, H = 330, L = 48, R = 34, T = 26, B = 46;
  const max = Math.max(20, ...rows.map(r => Math.max(r.holdout_mape_pct, r.baseline_mape_pct)));
  const x = i => L + (rows.length === 1 ? (W - L - R) / 2 : i * (W - L - R) / (rows.length - 1));
  const y = v => H - B - v / max * (H - T - B);
  const line = key => rows.map((r, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(r[key]).toFixed(1)}`).join(' ');
  const gate = S.D.summary?.gate_mape_pct ?? 15;
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;min-width:330px" role="img" aria-label="Holdout error per model version">
    <line x1="${L}" y1="${H - B}" x2="${W - R}" y2="${H - B}" stroke="var(--border2)"/>
    <line x1="${L}" y1="${T}" x2="${L}" y2="${H - B}" stroke="var(--border2)"/>
    <line x1="${L}" y1="${y(gate)}" x2="${W - R}" y2="${y(gate)}" stroke="var(--good)"
      stroke-width="1.4" stroke-dasharray="5 4"/>
    <text x="${L + 6}" y="${y(gate) - 6}" font-size="11" fill="var(--good)">gate: ${gate}%</text>
    <path d="${line('baseline_mape_pct')}" fill="none" stroke="var(--ink3)" stroke-width="2" stroke-dasharray="4 4"/>
    <path d="${line('holdout_mape_pct')}" fill="none" stroke="var(--accent)" stroke-width="2.6"/>
    ${rows.map((r, i) => `<circle cx="${x(i)}" cy="${y(r.holdout_mape_pct)}" r="4.5"
        fill="${r.gate_status === 'pass' ? 'var(--good)' : 'var(--accent)'}"/>
      <text x="${x(i)}" y="${H - B + 17}" text-anchor="middle" font-size="10.5" fill="var(--ink3)">${S.esc(String(r.model_version).split('-')[0])}</text>
      <text x="${x(i)}" y="${H - B + 31}" text-anchor="middle" font-size="10" fill="var(--ink3)">${r.n_train_rows} rows</text>
      <text x="${x(i)}" y="${y(r.holdout_mape_pct) - 10}" text-anchor="middle" font-size="11"
        fill="var(--ink2)" font-variant-numeric="tabular-nums">${n1(r.holdout_mape_pct)}%</text>`).join('')}
    <text x="${L}" y="${T - 4}" font-size="11" fill="var(--ink3)">holdout MAPE · dashed grey: OLS baseline</text>
  </svg>`;
}

window.SLIDES = [
  {id: 'title', kicker: 'ML · DATA ENGINEERING SCENARIO', render() {
    const s = S.D.summary || {};
    return `<div class="titleslide">
      <div class="kicker">Scenario walkthrough</div>
      <h2>Predict how long a query<br>will run before it runs.</h2>
      <div class="stackchips">
        <span class="schip hot">python</span><span class="schip hot">dbt</span>
        <span class="schip">duckdb</span><span class="schip">scikit-learn</span>
        <span class="schip">github actions</span>
      </div>
      <p class="lead">Warehouse work is queued, sized and priced on a guess: how long will this
        thing take. The pipeline measures ${S.fmtN(s.queries_measured || 0)} real queries on the
        runner, trains a gradient booster on features that are known before the query starts,
        and publishes the error with a confidence interval. Holdout MAPE
        ${n1(s.holdout_mape_pct)}% on ${s.n_holdout_rows || 0} unseen queries.</p>
      <div class="byline">${S.esc(S.CFG.author)}</div>
    </div>`;}},

  {id: 'assumptions', kicker: 'ASSUMPTIONS & STRATEGY', render() {
    const s = S.D.summary || {};
    return `<h2>Assumptions &amp; strategy</h2>
      <div class="ptsec">What I assumed</div>
      <ul class="pointlist">
        <li><span class="pt">1</span><span><b>Every feature is known before the query runs.</b>
          Table sizes, join count, group by, filter selectivity, order by, window,
          limit.</span></li>
        <li><span class="pt">2</span><span><b>A model predicts the hardware it trained on.</b>
          These numbers come from the machine that ran the pipeline: ${s.cpu_count || 4} vCPU,
          DuckDB threads pinned to ${s.duckdb_threads || 4}.</span></li>
        <li><span class="pt">3</span><span><b>The data is measured, not simulated.</b>
          ${S.fmtN(s.queries_measured || 0)} queries on tables of 2M to 8M rows, the median of
          ${s.reps_median || 5}+ timed repetitions after a warm-up.</span></li>
        <li><span class="pt">4</span><span><b>A shared runner drifts.</b> The same calibration
          query is re-timed every ten queries; each reading is divided by the value interpolated
          to its position.</span></li>
      </ul>
      <div class="ptsec">How it is built</div>
      <ul class="pointlist">
        <li><span class="pt">1</span><span><b>The gate is fixed before the numbers are known.</b>
          ${m(S.esc(s.gate_rule || 'holdout MAPE ≤ 15% and R² ≥ 0.90'))}. A model that misses it
          is published anyway, marked FAIL here and in ${m('dim_model_version')}.</span></li>
        <li><span class="pt">2</span><span><b>The interval is reported, not hidden.</b> 2,000
          bootstrap draws over the holdout errors give the 95% CI printed beside every MAPE.</span></li>
        <li><span class="pt">3</span><span><b>Retraining is a pipeline step.</b> Measure, train,
          ${m('dbt build')}, publish; not a notebook someone runs by hand.</span></li>
        <li><span class="pt">4</span><span><b>Layered like the warehouse.</b> stage → transform →
          conformed (keyed, incremental, tested) → datamart, so model output is queryable data,
          not a pickle in a bucket.</span></li>
      </ul>`;}},

  {id: 'arch', kicker: 'THE ARCHITECTURE', render() {
    return `<h2>The architecture</h2>
      <p class="lead">Run dispatches a GitHub Actions workflow: Python measures the next batch of
        queries, scikit-learn retrains on everything measured so far, dbt builds and tests, results
        are committed back as JSON. A real pipeline, driven from a web page.</p>
      <div class="diagram" style="position:relative">
        ${S.isNarrow() ? S.archFlow() : S.svgArch()}
        ${S.isNarrow() ? '' : `<button class="zoombtn" id="archZoomBtn">${S.archZoom ? '&#8854; full picture' : '&#8853; zoom to pipeline'}</button>`}
      </div>`;}},

  {id: 'lineage', kicker: 'DBT LINEAGE', render() {
    return `<h2>dbt lineage</h2>
      <p class="lead">Read from the dbt manifest after the last build, so the picture can never
        drift from the project. The model's output lands in a seed and is conformed like any
        other source.</p>
      <div class="diagram" style="margin:38px 0 26px">${S.isNarrow() ? S.dagFlow() : S.svgDag()}</div>
      ${S.dagLegend()}`;}},

  {id: 'code', kicker: 'THE CODE', render() {
    const files = S.D.models?.files || [];
    const lines = files.reduce((a, f) => a + f.sql.split('\n').length, 0);
    return `<h2>The code</h2>
      <p class="lead">${files.length} files, ~${Math.round(lines / 10) * 10} lines.
        ${m('scripts/make_workload.py')} builds the tables and the query catalogue,
        ${m('scripts/run.py')} times them, ${m('scripts/train.py')} fits and scores the model.
        Press ▶ on a model to see its rows from the last run.</p>
      ${S.ideHtml()}`;}},

  {id: 'accuracy', kicker: 'THE RESULT', render() {
    const s = S.D.summary || {};
    const rows = latestPredictions();
    const worst = rows.filter(r => r.abs_pct_error >= 30).length;
    return `<h2>Predicted against measured</h2>
      <p class="lead">Every point is one query, predicted out of sample: holdout queries by a model
        that never saw them, earlier queries by 5-fold cross-validation. Colour is the join count.
        Ringed points miss by 30% or more (${worst} of ${rows.length}).</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 16px">
        <span class="pill">holdout MAPE <b>${n1(s.holdout_mape_pct)}%</b>
          <span class="dim">95% CI ${n1(s.mape_ci_low_pct)}–${n1(s.mape_ci_high_pct)}</span></span>
        <span class="pill">R² <b>${n2(s.holdout_r2)}</b> <span class="dim">log10 s</span></span>
        <span class="pill">MAE <b>${s.holdout_mae_seconds == null ? '—' : Number(s.holdout_mae_seconds).toFixed(3)}s</b></span>
        <span class="pill">OLS baseline <b>${n1(s.baseline_mape_pct)}%</b></span>
        ${gateBadge()}
      </div>
      <div class="diagram">${scatterSvg()}</div>
      <div class="legend" style="margin-top:14px">
        ${['0 joins', '1 join', '2 joins', '3 joins'].map((label, i) =>
          `<span><span style="width:9px;height:9px;border-radius:50%;display:inline-block;
            background:${['var(--accent)', 'var(--good)', 'var(--warn)', 'var(--dup)'][i]}"></span>${label}</span>`).join('')}
        <span><span style="width:9px;height:9px;border-radius:50%;display:inline-block;
          border:2px solid var(--bad)"></span>30% error or worse</span>
      </div>`;}},

  {id: 'signal', kicker: 'WHY IT WORKS', render() {
    const s = S.D.summary || {};
    const versions = S.D.tables.dm_model_scorecard || [];
    const first = versions[0] || {}, last = versions[versions.length - 1] || {};
    const pane = (title, body) => `<div><div class="ptsec" style="margin:0 0 8px">${title}</div>
      <div style="overflow-x:auto">${body}</div></div>`;
    return `<h2>Why the signal is strong</h2>
      <p class="lead">Runtime is not a preference, it is physics: bytes read, rows hashed, rows
        sorted. Permutation importance agrees with the query plan: how much data survives the
        filter dominates, then whether there is a group by or a window over it. Retraining on every
        new batch moved the holdout error from ${n1(first.holdout_mape_pct)}% to
        ${n1(last.holdout_mape_pct)}%, against an OLS baseline on the same features that stayed
        near ${n1(s.baseline_mape_pct)}%.</p>
      <div style="display:grid;grid-template-columns:${S.isNarrow() ? '1fr' : '1fr 1fr'};gap:28px;align-items:start">
        ${pane('Permutation importance · holdout · log seconds', importanceSvg())}
        ${pane('Holdout MAPE per model version', learningSvg())}
      </div>`;}},

  {id: 'sla', kicker: 'WHAT IT IS FOR', render() {
    const s = S.D.summary || {};
    const all = S.D.tables.dm_runtime_sla || [];
    const rank = {missed_breach: 0, false_alarm: 1, breach_called: 2, inside_sla: 3};
    const rows = all.slice().sort((a, b) => rank[a.sla_verdict] - rank[b.sla_verdict]
      || b.worst_actual_seconds - a.worst_actual_seconds).slice(0, 11);
    const cls = {missed_breach: 'rowdup', false_alarm: 'rowimp'};
    const verdict = {missed_breach: ['missed breach', 'b-dup'], false_alarm: ['false alarm', 'b-dup'],
      breach_called: ['breach called', 'b-new'], inside_sla: ['inside SLA', 'b-crm']};
    return `<h2>What this is for</h2>
      <p class="lead">Admission control, pool sizing and cost. Before the query runs the model says
        whether the shape breaches the ${s.sla_seconds || 1}s SLA. Over ${all.length} shapes it
        called ${s.sla_breaches_called || 0} breaches correctly and missed
        ${s.sla_missed_breaches || 0}. A missed breach is a page at 3am; a false alarm is a pool
        sized too big. The rows that got it wrong are first.</p>
      <div class="verdicts scrollbox"><table>
        <thead><tr><th>Shape</th><th>Predicted p50</th><th>Measured p50</th><th>Worst measured</th>
          <th>Verdict</th></tr></thead>
        <tbody>${rows.map(r => `<tr${cls[r.sla_verdict] ? ` class="${cls[r.sla_verdict]}"` : ''}>
          <td>${S.esc(r.template_label)}</td>
          <td class="num mono">${Number(r.p50_predicted_seconds).toFixed(3)}s</td>
          <td class="num mono">${Number(r.p50_actual_seconds).toFixed(3)}s</td>
          <td class="num mono">${Number(r.worst_actual_seconds).toFixed(3)}s</td>
          <td>${S.badge(verdict[r.sla_verdict][0], verdict[r.sla_verdict][1])}</td>
        </tr>`).join('')}</tbody></table></div>`;}},
];

/* Console tabs for this scenario.
   tabs:    [{key, label, count()}]  in display order
   render:  {key: () => html}        S.tablePanel / S.incomingPanel are generic
   afterRun(action) -> tab key to show when a run finishes
   toast(action, before, after) -> message after a run */
'use strict';
const gateBadgeCell = v => v === 'pass'
  ? S.badge('PASS', 'b-new', S.ICO.check) : S.badge('FAIL', 'b-dup');
const secs = v => v == null ? '—' : `${Number(v).toFixed(3)}s`;
const pct = v => v == null ? '—' : `${Number(v).toFixed(1)}%`;

function latestVersion() { return S.D.summary?.model_version || null; }
function predictionRows() { return S.D.tables.predictions || []; }

/* The queue: the next batch of queries, with the runtime the published model
   expects. Nothing here has been run. The next run measures these same queries,
   so the claim in the last column is checkable. */
function incomingPanel() {
  const next = S.D.next;
  if (!next?.name) {
    return `<div class="card"><div class="empty"><div class="big">✦</div>
      <b>Every batch has been measured.</b><br>
      <button class="btn btn-primary" id="resetBtn2">Reset the demo ↺</button></div></div>`;
  }
  const scored = next.rows.length && next.rows[0].predicted_seconds != null;
  const rows = next.rows.map((r, i) => `<tr>
    <td class="num faded">${i + 1}</td>
    <td class="mono">${S.esc(r.query_id)}</td>
    <td>${S.esc(r.template_label)}</td>
    <td class="num">${S.fmtN(r.rows_in)}</td>
    <td class="num">${S.esc(r.n_joins)}</td>
    <td class="num">${S.esc(r.selectivity)}</td>
    <td class="num faded">${S.esc(r.limit_rows) === '0' ? '—' : S.esc(r.limit_rows)}</td>
    <td class="num mono">${scored ? secs(r.predicted_seconds) : '<span class="dim">no model yet</span>'}</td>
    <td class="dim">not run yet</td></tr>`).join('');
  return `<div class="card"><div class="cardhead">
      <h2><span class="mono">incoming/${S.esc(next.name)}.csv</span></h2>
      <span class="hint">${scored
        ? `scored by model ${S.esc(latestVersion())} before anything runs`
        : 'features known before anything runs'}</span></div>
    ${S.tableHTML(['#', 'query', 'shape', 'rows in', 'joins', 'selectivity', 'limit',
                   'predicted', 'measured'], rows)}
    <div class="loadbar">${S.runButton('loadBtn')}</div></div>`;
}

function predictionPanel() {
  const rows = predictionRows();
  if (!rows.length) {
    return `<div class="card"><div class="empty"><div class="big">∅</div>
      No model has been trained yet.</div></div>`;
  }
  const shown = rows.slice().sort((a, b) => b.abs_pct_error - a.abs_pct_error);
  const body = shown.map(r => `<tr${r.abs_pct_error >= 30 ? ' class="rowdup"' : ''}>
    <td class="mono">${S.esc(r.query_id)}</td>
    <td>${S.esc(r.template_label)}</td>
    <td class="num mono">${secs(r.actual_seconds)}</td>
    <td class="num mono">${secs(r.predicted_seconds)}</td>
    <td>${S.meter(r.abs_pct_error / 100)}</td>
    <td>${r.prediction_scope === 'holdout'
      ? S.badge('holdout', 'b-new') : S.badge('cross-validated', 'b-crm')}</td></tr>`).join('');
  return `<div class="card"><div class="cardhead">
      <h2 class="mono">data/predictions.csv</h2>
      <span class="hint">model ${S.esc(latestVersion() || '')} · out of sample · worst first · rows over 30% error highlighted</span></div>
    ${S.tableHTML(['query', 'shape', 'measured', 'predicted', 'error · share of actual',
                   'scored by'], body)}</div>`;
}

function modelVersionPanel() {
  const rows = S.D.tables.model_versions || [];
  if (!rows.length) {
    return `<div class="card"><div class="empty"><div class="big">∅</div>
      No model has been trained yet.</div></div>`;
  }
  const body = rows.map(r => `<tr${r.model_version === latestVersion() ? ' class="rowimp"' : ''}>
    <td class="mono"><b>${S.esc(r.model_version)}</b></td>
    <td class="num">${r.batches_measured}</td>
    <td class="num">${r.n_train_rows} / ${r.n_holdout_rows}</td>
    <td class="num"><b>${pct(r.holdout_mape_pct)}</b></td>
    <td class="num faded">${pct(r.mape_ci_low_pct)} – ${pct(r.mape_ci_high_pct)}</td>
    <td class="num">${Number(r.holdout_r2).toFixed(3)}</td>
    <td class="num mono">${secs(r.holdout_mae_seconds)}</td>
    <td class="num faded">${pct(r.baseline_mape_pct)}</td>
    <td>${gateBadgeCell(r.gate_status)}</td></tr>`).join('');
  return `<div class="card"><div class="cardhead">
      <h2 class="mono">data/model_versions.csv</h2>
      <span class="hint">one row per training run · gate: ${S.esc(S.D.summary?.gate_rule || '')}</span></div>
    ${S.tableHTML(['version', 'batches', 'train / holdout', 'MAPE', '95% CI', 'R²', 'MAE',
                   'OLS baseline', 'gate'], body)}</div>`;
}

function modelCardPanel() {
  const text = S.D.summary?.model_card || '';
  if (!text) {
    return `<div class="card"><div class="empty"><div class="big">∅</div>
      No model card published yet.</div></div>`;
  }
  return `<div class="card"><div class="cardhead"><h2 class="mono">artifacts/model_card.md</h2>
      <span class="hint">written on every run, committed with the model</span></div>
    ${S.codePanel('model_card.md', 'markdown', text, 'yml', 620)}</div>`;
}

/* The published model, run in the visitor's browser. Same widget as the "Try it"
   slide; the mount happens after this HTML is in the DOM. */
function tryItPanel() {
  setTimeout(() => window.TRYIT.mount(), 0);
  return `<div class="card"><div class="cardhead">
      <h2>try it</h2>
      <span class="hint">docs/data/model.onnx · scored in your browser, no server and no token</span></div>
    <div style="padding:20px">${window.TRYIT.html()}</div></div>`;
}

window.PANELS = {
  tabs: [
    {key: 'incoming', label: 'incoming batch', count: () => S.D.next?.name ? S.D.next.rows.length : 0},
    {key: 'try_it', label: 'try it', count: () => ''},
    {key: 'predictions', label: 'predictions', count: () => predictionRows().length},
    {key: 'model_versions', label: 'model versions', count: () => (S.D.tables.model_versions || []).length},
    {key: 'sla', label: 'sla', count: () => (S.D.tables.sla || []).length},
    {key: 'model_card', label: 'model card', count: () => ''},
  ],
  render: {
    try_it: () => tryItPanel(),
    incoming: () => incomingPanel(),
    predictions: () => predictionPanel(),
    model_versions: () => modelVersionPanel(),
    sla: () => S.tablePanel('sla', 'every shape against the SLA, called before the query runs',
      {rowClass: r => r.sla_verdict === 'missed_breach' ? 'rowdup'
        : r.sla_verdict === 'false_alarm' ? 'rowimp' : ''}),
    model_card: () => modelCardPanel(),
  },
  afterRun: action => action === S.CFG.actions.reset ? 'incoming' : 'predictions',
  toast: (action, before, after) => {
    if (action === S.CFG.actions.reset) return 'Demo reset ↺';
    const parts = [];
    const added = (after.queries_measured ?? 0) - (before.queries_measured ?? 0);
    if (added > 0) parts.push(`<b>${added}</b> queries measured`);
    if (after.model_version && after.model_version !== before.model_version) {
      parts.push(`model <b>${after.model_version}</b> · MAPE <b>${Number(after.holdout_mape_pct).toFixed(1)}%</b>`
        + ` · ${after.passes_gate ? 'gate PASS' : 'gate FAIL'}`);
    }
    return parts.length ? parts.join(' · ') : 'Run complete';
  },
};

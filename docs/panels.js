/* Console tabs for this scenario.
   tabs:    [{key, label, count()}]  in display order
   render:  {key: () => html}        S.tablePanel / S.incomingPanel are generic
   afterRun(action) -> tab key to show when a run finishes
   toast(action, before, after) -> message after a run */
'use strict';
const gateBadgeCell = v => v === 'pass'
  ? S.badge('PASS', 'b-new', S.ICO.check) : S.badge('FAIL', 'b-dup');
const ms = v => v == null ? '—' : `${Number(v).toFixed(1)} ms`;
const pct = v => v == null ? '—' : `${Number(v).toFixed(1)}%`;
const nul = '<span class="dim">NULL</span>';

function latestVersion() { return S.D.summary?.model_version || null; }
function predictionRows() { return S.D.tables.predictions || []; }
function historyRows() { return S.D.tables.query_history || []; }

/* The measured columns first, then the layout order. The point of the tab is
   that the header is ACCOUNT_USAGE's header, so nothing is dropped: the rest
   scrolls sideways, NULL included. */
const QH_FIRST = ['QUERY_TAG', 'WAREHOUSE_SIZE', 'EXECUTION_TIME', 'COMPILATION_TIME',
  'TOTAL_ELAPSED_TIME', 'ROWS_PRODUCED', 'PARTITIONS_TOTAL', 'BYTES_SCANNED',
  'QUERY_TYPE', 'EXECUTION_STATUS', 'START_TIME', 'QUERY_ID'];

function queryHistoryPanel() {
  const rows = historyRows();
  const columns = S.D.summary?.query_history_columns || [];
  if (!rows.length) {
    return `<div class="card"><div class="empty"><div class="big">∅</div>
      Nothing measured yet. <span class="dim">${columns.length} columns, no rows.</span></div></div>`;
  }
  const order = QH_FIRST.concat(columns.filter(c => !QH_FIRST.includes(c)));
  const nulls = columns.filter(c => rows.every(r => r[c] == null)).length;
  const cell = (c, v) => {
    if (v == null || v === '') return nul;
    if (c === 'QUERY_TEXT') return `<span class="mono" title="${S.esc(v)}">${S.esc(String(v).replace(/\s+/g, ' ').slice(0, 70))}…</span>`;
    if (c === 'EXECUTION_TIME' || c === 'TOTAL_ELAPSED_TIME' || c === 'COMPILATION_TIME')
      return `<span class="num mono">${Number(v).toFixed(1)}</span>`;
    if (typeof v === 'number') return `<span class="num">${S.fmtN(v)}</span>`;
    return S.esc(String(v).length > 40 ? `${String(v).slice(0, 40)}…` : v);
  };
  const body = rows.map(r => `<tr>${order.map(c => `<td>${cell(c, r[c])}</td>`).join('')}</tr>`).join('');
  return `<div class="card"><div class="cardhead">
      <h2 class="mono">data/query_history.csv</h2>
      <span class="hint">the layout of <span class="mono">SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY</span>
        · ${columns.length} columns, ${nulls} of them NULL because a local engine has nothing
        to report · scrolls sideways</span></div>
    ${S.tableHTML(order, body)}</div>`;
}

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
  const scored = next.rows.length && next.rows[0].predicted_ms != null;
  const flags = r => [r.has_group_by ? 'group by' : '', r.has_order_by ? 'order by' : '',
    r.has_window ? 'window' : ''].filter(Boolean).join(' · ') || '—';
  const rows = next.rows.map((r, i) => `<tr>
    <td class="num faded">${i + 1}</td>
    <td class="mono">${S.esc(r.query_id)}</td>
    <td>${S.esc(r.warehouse_size)}</td>
    <td class="num">${S.fmtN(r.table_rows)}</td>
    <td class="num">${S.esc(r.n_joins)}</td>
    <td class="faded">${flags(r)}</td>
    <td class="num faded">${r.limit_rows ? S.fmtN(r.limit_rows) : '—'}</td>
    <td class="num faded">${S.esc(r.predicate_literal)}</td>
    <td>${r.seen_before ? S.badge('seen', 'b-crm') : '<span class="dim">new</span>'}</td>
    <td class="num mono">${scored ? ms(r.predicted_ms) : '<span class="dim">no model yet</span>'}</td>
    <td class="dim">not run yet</td></tr>`).join('');
  return `<div class="card"><div class="cardhead">
      <h2><span class="mono">incoming/${S.esc(next.name)}.csv</span></h2>
      <span class="hint">${scored
        ? `scored by model ${S.esc(latestVersion())} before anything runs`
        : 'parsed from the SQL text before anything runs'}</span></div>
    ${S.tableHTML(['#', 'query', 'warehouse', 'rows in tables', 'joins', 'clauses',
                   'limit', 'filter <', 'shape', 'predicted', 'measured'], rows)}
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
    <td class="mono">${S.esc(r.query_id).slice(0, 8)}</td>
    <td>${S.esc(r.template_label)}</td>
    <td>${S.esc(r.warehouse_size)}</td>
    <td class="num mono">${ms(r.actual_ms)}</td>
    <td class="num mono">${ms(r.predicted_ms)}</td>
    <td>${S.meter(r.abs_pct_error / 100)}</td>
    <td>${r.prediction_scope === 'holdout'
      ? S.badge('holdout', 'b-new') : S.badge('cross-validated', 'b-crm')}</td></tr>`).join('');
  return `<div class="card"><div class="cardhead">
      <h2 class="mono">data/predictions.csv</h2>
      <span class="hint">model ${S.esc(latestVersion() || '')} · out of sample · worst first · rows over 30% error highlighted</span></div>
    ${S.tableHTML(['query id', 'shape', 'warehouse', 'measured', 'predicted',
                   'error · share of actual', 'scored by'], body)}</div>`;
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
    <td class="num mono">${ms(r.holdout_mae_ms)}</td>
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
    {key: 'query_history', label: 'query_history', count: () => historyRows().length},
    {key: 'tables', label: 'tables', count: () => (S.D.tables.tables || []).length},
    {key: 'predictions', label: 'predictions', count: () => predictionRows().length},
    {key: 'model_versions', label: 'model versions', count: () => (S.D.tables.model_versions || []).length},
    {key: 'sla', label: 'sla', count: () => (S.D.tables.sla || []).length},
    {key: 'model_card', label: 'model card', count: () => ''},
  ],
  render: {
    try_it: () => tryItPanel(),
    incoming: () => incomingPanel(),
    query_history: () => queryHistoryPanel(),
    tables: () => S.tablePanel('tables',
      'the layout of SNOWFLAKE.ACCOUNT_USAGE.TABLES · ROW_COUNT and BYTES measured off the database'),
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

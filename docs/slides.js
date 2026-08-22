/* Slides for this scenario. Each slide: {id, kicker, render() -> html}.
   S exposes shell helpers and the live data (S.D), config (S.CFG).
   Every number on these slides comes from docs/data/*.json. */
'use strict';
const m = t => `<span class="mono">${t}</span>`;
const n1 = v => v == null ? '—' : Number(v).toFixed(1);
const n2 = v => v == null ? '—' : Number(v).toFixed(2);
const msLabel = v => v == null ? '—' : `${Number(v).toFixed(1)} ms`;

/* Predictions from the model that is currently published. report.py has already
   restricted them to the latest version and attached the query shape. */
function latestPredictions() {
  return S.D.tables.predictions || [];
}
function gateBadge() {
  const s = S.D.summary || {};
  if (s.passes_gate == null) return S.badge('no model yet', 'b-dup');
  return s.passes_gate ? S.badge('GATE PASS', 'b-new', S.ICO.check)
                       : S.badge('GATE FAIL', 'b-dup');
}

/* Predicted against actual, both on log axes, with the 45 degree line.
   Drawn here from data/predictions.csv rather than shipped as an image, so it
   cannot disagree with the table two tabs away.
   `mark` is a predicted runtime from the try-it widget: it has no measured
   counterpart, so it is drawn on the diagonal, which is where a prediction sits
   before the query has been run. */
function scatterSvg(mark) {
  const rows = latestPredictions().filter(r => r.actual_ms > 0 && r.predicted_ms > 0);
  if (!rows.length) return '<div class="empty">No predictions published yet.</div>';
  const W = 880, H = 400, L = 84, R = 20, T = 20, B = 44;
  const values = rows.flatMap(r => [r.actual_ms, r.predicted_ms]);
  if (mark > 0) values.push(mark);
  const lo = Math.log10(Math.min(...values)) - 0.08, hi = Math.log10(Math.max(...values)) + 0.08;
  const x = v => L + (Math.log10(v) - lo) / (hi - lo) * (W - L - R);
  const y = v => H - B - (Math.log10(v) - lo) / (hi - lo) * (H - T - B);
  const ticks = [];
  for (let e = Math.ceil(lo); e <= Math.floor(hi); e++) ticks.push(Math.pow(10, e));
  const colour = ['var(--accent)', 'var(--good)', 'var(--warn)', 'var(--dup)'];
  const dots = rows.map(r => {
    const worst = r.abs_pct_error >= 30;
    return `<circle cx="${x(r.actual_ms).toFixed(1)}" cy="${y(r.predicted_ms).toFixed(1)}"
      r="${worst ? 5 : 3.6}" fill="${colour[Math.min(3, r.n_joins)]}"
      fill-opacity="${worst ? 0.95 : 0.6}" stroke="${worst ? 'var(--bad)' : 'none'}"
      stroke-width="1.6"><title>${S.esc(r.template_label)} · ${S.esc(r.warehouse_size)}
measured ${Number(r.actual_ms).toFixed(1)} ms · predicted ${Number(r.predicted_ms).toFixed(1)} ms · ${n1(r.abs_pct_error)}%</title></circle>`;
  }).join('');
  const grid = ticks.map(t => `
    <line x1="${x(t)}" y1="${T}" x2="${x(t)}" y2="${H - B}" stroke="var(--border)" stroke-width="1"/>
    <line x1="${L}" y1="${y(t)}" x2="${W - R}" y2="${y(t)}" stroke="var(--border)" stroke-width="1"/>
    <text x="${x(t)}" y="${H - B + 18}" text-anchor="middle" font-size="11" fill="var(--ink3)">${t} ms</text>
    <text x="${L - 10}" y="${y(t) + 4}" text-anchor="end" font-size="11" fill="var(--ink3)">${t} ms</text>`).join('');
  const corner = Math.pow(10, lo), far = Math.pow(10, hi);
  const left = mark > 0 && x(mark) > W * 0.66;
  const marker = mark > 0 ? `
    <line x1="${L}" y1="${y(mark)}" x2="${W - R}" y2="${y(mark)}" stroke="var(--accent-deep)"
      stroke-width="1.3" stroke-dasharray="4 4" opacity="0.75"/>
    <circle cx="${x(mark)}" cy="${y(mark)}" r="9" fill="none" stroke="var(--accent-deep)" stroke-width="2.4"/>
    <circle cx="${x(mark)}" cy="${y(mark)}" r="3.4" fill="var(--accent-deep)"/>
    <text x="${x(mark) + (left ? -15 : 15)}" y="${y(mark) - 12}" font-size="12" font-weight="700"
      text-anchor="${left ? 'end' : 'start'}" fill="var(--accent-deep)">your query · ${mark.toFixed(0)} ms</text>` : '';
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Predicted against actual runtime">
    ${grid}
    <line x1="${x(corner)}" y1="${y(corner)}" x2="${x(far)}" y2="${y(far)}"
      stroke="var(--ink3)" stroke-width="1.4" stroke-dasharray="6 5"/>
    ${dots}${marker}
    <text x="${L + 8}" y="${T + 12}" font-size="11" fill="var(--ink3)">dashed line: a perfect prediction</text>
    <text x="${W - R}" y="${H - 6}" text-anchor="end" font-size="11.5" fill="var(--ink2)">measured EXECUTION_TIME (log ms)</text>
    <text x="14" y="${T + 4}" font-size="11.5" fill="var(--ink2)" transform="rotate(-90 14 ${T + 4})" text-anchor="end">predicted (log ms)</text>
  </svg>`;
}

/* Permutation importance, holdout, in log ms. */
function importanceSvg() {
  const rows = (S.D.summary?.importances || []).filter(r => r.importance > 0).slice(0, 8);
  if (!rows.length) return '<div class="empty">No model published yet.</div>';
  const max = Math.max(...rows.map(r => r.importance));
  const W = 540, rowH = 46, H = rows.length * rowH + 14;
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;min-width:330px" role="img" aria-label="Feature importance">
    ${rows.map((r, i) => {
      const w = Math.max(2, r.importance / max * 280);
      return `<rect x="196" y="${i * rowH + 12}" width="${w}" height="20" rx="4"
          fill="${i === 0 ? 'var(--accent)' : 'var(--accent-2)'}" fill-opacity="${1 - i * 0.09}"/>
        <text x="186" y="${i * rowH + 27}" text-anchor="end" font-size="12.5"
          fill="var(--ink2)" font-family="ui-monospace,monospace">${S.esc(r.feature)}</text>
        <text x="${200 + w + 8}" y="${i * rowH + 27}" font-size="12.5" fill="var(--ink3)"
          font-variant-numeric="tabular-nums">${r.importance.toFixed(3)}</text>`;
    }).join('')}
  </svg>`;
}

/* The learning curve: holdout MAPE per model version as batches accumulate. */
function learningSvg() {
  const rows = (S.D.tables.model_versions || []).slice();
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

/* ---------- reading a query's shape out of its text ----------
   The same eight structural questions src/runtime_model/parse.py asks, in the
   same order, so the widget's feature vector is built the way the training
   rows were: write the SQL, then read it back. */
const RX = {
  comment: /--[^\n]*|\/\*[\s\S]*?\*\//g,
  cte: /(?:\bwith\b|,)\s*([a-z_][a-z0-9_]*)\s+as\s*\(/gi,
  fromJoin: /\b(?:from|join)\s+([a-z_][a-z0-9_.]*)/gi,
  join: /\bjoin\b/gi,
  groupBy: /\bgroup\s+by\b/i,
  orderBy: /\border\s+by\b/i,
  window: /\bover\s*\(/i,
  limit: /\blimit\s+(\d+)/gi,
  conjunction: /\b(?:and|or)\b/gi,
  comparison: /(?:<=|>=|<>|!=|<|>|=)\s*(-?\d+(?:\.\d+)?)/g,
  where: /\bwhere\b/gi,
  clauseEnd: /\b(?:group\s+by|order\s+by|having|limit|window|qualify)\b/iy,
};
const all = (re, text) => { re.lastIndex = 0; return [...text.matchAll(re)]; };

/* A where clause contains brackets of its own -- cast(substr(x, 3, 3)) < 450 --
   so it is cut by depth, not by the first close bracket. */
function whereClauses(text) {
  const clauses = [];
  for (const match of all(RX.where, text)) {
    const start = match.index + match[0].length;
    let depth = 0, i = start;
    for (; i < text.length; i++) {
      const c = text[i];
      if (c === '(') depth++;
      else if (c === ')') { if (depth === 0) break; depth--; }
      else if (depth === 0) { RX.clauseEnd.lastIndex = i; if (RX.clauseEnd.test(text)) break; }
    }
    clauses.push(text.slice(start, i));
  }
  return clauses;
}

function parseQueryText(sql) {
  const text = sql.replace(RX.comment, ' ');
  const ctes = new Set(all(RX.cte, text).map(m => m[1].toLowerCase()));
  const tables = [];
  for (const match of all(RX.fromJoin, text)) {
    const name = match[1].split('.').pop().toLowerCase();
    if (!ctes.has(name) && !tables.includes(name.toUpperCase())) tables.push(name.toUpperCase());
  }
  const clauses = whereClauses(text);
  const predicates = clauses.reduce((a, c) => a + 1 + all(RX.conjunction, c).length, 0);
  const literals = clauses.flatMap(c => all(RX.comparison, c).map(m => Number(m[1])));
  const limits = all(RX.limit, text).map(m => Number(m[1]));
  return {
    tables, n_tables: tables.length, n_joins: all(RX.join, text).length,
    has_group_by: RX.groupBy.test(text) ? 1 : 0,
    has_order_by: RX.orderBy.test(text) ? 1 : 0,
    has_window: RX.window.test(text) ? 1 : 0,
    limit_rows: limits.length ? Math.max(...limits) : 0,
    n_predicates: predicates,
    predicate_literal: literals.length ? Math.max(...literals) : 0,
  };
}

/* ---------- try it ----------
   The model that the pipeline published, run in the visitor's browser through
   onnxruntime-web. docs/data/model.onnx and model_meta.json are written by the
   training step on the runner, so this widget and the scatter above it are the
   same model. Nothing is sent anywhere: no server, no token.
   The slide and the console tab share this one object. */
const ORT_VERSION = '1.27.0';
const ORT_BASE = `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_VERSION}/dist/`;

const TRY = {
  status: 'idle',            // idle | loading | ready | error
  message: '',
  meta: null, session: null, ms: null, outside: [],
  input: {table: 2, joins: 1, group_by: 1, order_by: 0, window: 0, literal: 450,
          limit: 0, warehouse: 2},
};
const fmtRows = v => v >= 1e6 ? `${(v / 1e6).toFixed(2)}M` : v >= 1e3 ? `${Math.round(v / 1e3)}k` : String(v);
const fmtMB = v => `${(v / 1e6).toFixed(0)} MB`;

/* ?try=joins=3;window=1;warehouse=0 — a deterministic starting shape, so a
   screenshot or a link can show a query other than the default one. */
function tryQueryOverride() {
  const raw = new URLSearchParams(location.search).get('try');
  if (!raw) return;
  for (const pair of raw.split(/[;,&]/)) {
    const [key, value] = pair.split('=');
    const number = Number(value);
    if (key && isFinite(number) && key in TRY.input) TRY.input[key] = number;
  }
}
tryQueryOverride();

function factTables() {
  return TRY.meta.warehouse.tables.filter(t => t.name.startsWith(TRY.meta.warehouse.fact_prefix));
}
function dimTables() {
  const by = Object.fromEntries(TRY.meta.warehouse.tables.map(t => [t.name, t]));
  return TRY.meta.warehouse.join_dims.map(name => by[name]).filter(Boolean);
}

/* The statement the controls describe, written the way workload.py writes the
   catalogue. It is what gets parsed, and it is shown next to the number. */
function trySql() {
  const fact = factTables()[Math.min(TRY.input.table, factTables().length - 1)];
  const dims = dimTables().slice(0, TRY.input.joins);
  const keys = {DIM_CUSTOMER_WL: 'customer_id', DIM_PRODUCT_WL: 'product_id',
                DIM_REGION_WL: 'region_id'};
  const attributes = {DIM_CUSTOMER_WL: 'customer_segment', DIM_PRODUCT_WL: 'product_category',
                      DIM_REGION_WL: 'region_name'};
  const lower = n => n.toLowerCase();
  const projected = dims.map(d => `            ${lower(d.name)}.${attributes[d.name]}`)
    .concat(['            fact_event.customer_id', '            fact_event.product_id',
             '            fact_event.amount']);
  const joins = dims.map(d =>
    `        inner join ${lower(d.name)} on fact_event.${keys[d.name]} = ${lower(d.name)}.${keys[d.name]}`);
  const filtered = ['        select', projected.join(',\n'),
    `        from ${lower(fact.name)} as fact_event`, ...joins,
    '        where cast(substr(fact_event.event_code, 3, 3) as integer)',
    `            < ${TRY.input.literal}`];
  const ctes = [['filtered', filtered.join('\n')]];
  let source = 'filtered';
  if (TRY.input.window) {
    ctes.push(['ranked', ['        select', '            filtered.*,',
      '            row_number() over (', '                partition by filtered.customer_id',
      '                order by filtered.amount desc', '            ) as amount_rank',
      '        from filtered'].join('\n')]);
    source = 'ranked';
  }
  const groups = TRY.input.group_by
    ? dims.map(d => attributes[d.name]).concat(['customer_id']) : [];
  const measures = ['        count(*) as query_rows', '        sum(amount) as amount_total',
                    '        count(distinct product_id) as products'];
  if (TRY.input.window) measures.push('        max(amount_rank) as deepest_rank');
  const final = ['    select',
    groups.map(g => `        ${g}`).concat(measures).join(',\n'), `    from ${source}`];
  if (groups.length) final.push(`    group by ${groups.join(', ')}`);
  if (TRY.input.order_by) final.push('    order by amount_total desc');
  if (TRY.input.limit) final.push(`    limit ${TRY.input.limit}`);
  return `with\n${ctes.map(([n, b]) => `    ${n} as (\n${b}\n    )`).join(',\n\n')}\n\n${final.join('\n')}`;
}

/* Same order and same transforms as src/runtime_model/features.py. The last two
   features say "we have never seen this shape": the widget scores your query
   cold, with no history behind it. */
function tryFeatures() {
  const sql = trySql();
  const parsed = parseQueryText(sql);
  const sizes = Object.fromEntries(TRY.meta.warehouse.tables.map(t => [t.name, t]));
  const known = parsed.tables.map(name => sizes[name]).filter(Boolean);
  const rows = known.reduce((a, t) => a + t.rows, 0);
  const bytes = known.reduce((a, t) => a + t.bytes, 0);
  const warehouse = TRY.meta.warehouse.sizes[TRY.input.warehouse];
  const vector = [
    Math.log10(Math.max(rows, 1)), Math.log10(Math.max(bytes, 1)),
    parsed.n_tables, parsed.n_joins, parsed.has_group_by, parsed.has_order_by,
    parsed.has_window, Math.log10(parsed.limit_rows + 1), parsed.n_predicates,
    parsed.predicate_literal, warehouse.threads, 0, 0,
  ];
  return {vector, sql, parsed, rows, bytes, warehouse};
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const el = document.createElement('script');
    el.src = src; el.onload = resolve;
    el.onerror = () => reject(new Error('could not load onnxruntime-web from the CDN'));
    document.head.appendChild(el);
  });
}

/* Lazy: nothing is fetched until the widget is on screen for the first time. */
async function tryLoad() {
  if (TRY.status === 'loading' || TRY.status === 'ready') return;
  TRY.status = 'loading'; paintTry();
  try {
    const response = await fetch(`data/model_meta.json?t=${Date.now()}`, {cache: 'no-store'});
    if (!response.ok) throw new Error('no model is published yet — run the pipeline once');
    const meta = await response.json();
    if (!window.ort) await loadScript(`${ORT_BASE}ort.min.js`);
    ort.env.wasm.wasmPaths = ORT_BASE;
    ort.env.wasm.numThreads = 1;
    ort.env.logLevel = 'error';
    const bytes = await (await fetch(`data/model.onnx?v=${encodeURIComponent(meta.model_version)}`)).arrayBuffer();
    TRY.session = await ort.InferenceSession.create(bytes, {executionProviders: ['wasm']});
    TRY.meta = meta;
    TRY.input.joins = Math.max(0, Math.min(meta.warehouse.join_dims.length, TRY.input.joins));
    TRY.input.warehouse = Math.max(0, Math.min(meta.warehouse.sizes.length - 1, TRY.input.warehouse));
    TRY.status = 'ready';
    await tryPredict();
  } catch (error) {
    TRY.status = 'error';
    TRY.message = error && error.message ? error.message : String(error);
    paintTry();
  }
}

async function tryPredict() {
  if (TRY.status !== 'ready') return;
  const f = tryFeatures();
  try {
    const tensor = new ort.Tensor('float32', Float32Array.from(f.vector), [1, f.vector.length]);
    const out = await TRY.session.run({[TRY.meta.input_name]: tensor});
    TRY.ms = Math.exp(Number(out[TRY.meta.output_name].data[0]));
    // The published ranges are rounded, so compare with a slack wider than that.
    TRY.outside = TRY.meta.features.filter((name, i) => {
      const range = TRY.meta.feature_ranges[name];
      return f.vector[i] < range.min - 1e-5 || f.vector[i] > range.max + 1e-5;
    });
  } catch (error) {
    TRY.status = 'error';
    TRY.message = error && error.message ? error.message : String(error);
  }
  paintTry();
}

function tryNotice() {
  if (TRY.status === 'error') {
    return `<div class="card"><div class="empty"><div class="big">⚠</div>
      <b>The in-browser model did not start.</b><br>${S.esc(TRY.message)}.<br>
      <span class="dim">The numbers on the rest of the page are unaffected: they come from
      the pipeline, not from this widget.</span></div></div>`;
  }
  return `<div class="card"><div class="empty"><span class="spin"></span>
    Loading the model into your browser…</div></div>`;
}

const tryToggle = (key, label) => `<label style="display:flex;align-items:center;gap:9px;
  padding:9px 12px;border:1px solid var(--border);border-radius:11px;background:var(--surface);
  cursor:pointer;font-size:13px;font-weight:600">
  <input type="checkbox" data-try="${key}" ${TRY.input[key] ? 'checked' : ''}>${label}</label>`;

const trySlider = (key, label, value, min, max, step) => `<label style="display:block">
  <span style="display:flex;justify-content:space-between;gap:10px;font-size:12px;color:var(--ink2)">
    <span>${label}</span><span class="mono" id="try_v_${key}"><b>${value}</b></span></span>
  <input type="range" data-try="${key}" min="${min}" max="${max}" step="${step}"
    value="${TRY.input[key]}" style="width:100%;margin:4px 0 0;accent-color:var(--accent)"></label>`;

function tryFormHtml() {
  const warehouse = TRY.meta.warehouse;
  const sizes = warehouse.sizes.map((s, i) =>
    `<option value="${i}" ${i === TRY.input.warehouse ? 'selected' : ''}>${S.esc(s.name)} · ${s.threads} thread${s.threads === 1 ? '' : 's'}</option>`).join('');
  const tables = factTables().map((t, i) =>
    `<option value="${i}" ${i === TRY.input.table ? 'selected' : ''}>${S.esc(t.name)} · ${fmtRows(t.rows)} rows · ${fmtMB(t.bytes)}</option>`).join('');
  const limits = warehouse.limits.map(v =>
    `<option value="${v}" ${v === TRY.input.limit ? 'selected' : ''}>${v ? `limit ${v}` : 'no limit'}</option>`).join('');
  const select = (key, options, label) => `<label style="display:block">
    <span style="font-size:12px;color:var(--ink2)">${label}</span>
    <select data-try="${key}" style="width:100%;margin-top:4px;font:inherit;font-size:13px;
      padding:9px 11px;border-radius:11px;border:1px solid var(--border);
      background:var(--surface);color:var(--ink)">${options}</select></label>`;
  return `<div style="display:grid;grid-template-columns:${S.isNarrow() ? '1fr' : 'minmax(0,1.15fr) minmax(280px,.85fr)'};
      gap:22px;align-items:start">
    <div id="try_form">
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:16px 20px">
        ${select('warehouse', sizes, 'WAREHOUSE_SIZE')}
        ${select('table', tables, 'table scanned')}
        ${select('limit', limits, 'limit')}
        ${trySlider('joins', 'joins to dimensions', TRY.input.joins, 0, warehouse.join_dims.length, 1)}
        ${trySlider('literal', 'filter constant', TRY.input.literal, 20, 900, 10)}
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:16px">
        ${tryToggle('group_by', 'group by')}${tryToggle('order_by', 'order by')}${tryToggle('window', 'window')}
      </div>
      <div class="dim" style="font-size:12px;margin-top:14px" id="try_derived"></div>
      <div class="dim" style="font-size:11.5px;margin-top:6px">
        trained on ${TRY.meta.n_rows} measured queries. Your query is scored cold: no
        prior for its QUERY_PARAMETERIZED_HASH.</div>
    </div>
    <div id="try_out"></div>
  </div>
  <div id="try_sql" style="margin-top:20px"></div>
  <div class="diagram" id="try_plot" style="margin-top:22px"></div>`;
}

function tryOutHtml() {
  const meta = TRY.meta, value = TRY.ms;
  const sla = Number(S.D.summary?.sla_ms || 0);
  const verdict = !sla ? '' : value > sla
    ? S.badge(`breaches the ${sla} ms SLA`, 'b-dup')
    : S.badge(`inside the ${sla} ms SLA`, 'b-new', S.ICO.check);
  const note = TRY.outside.length ? `<div style="font-size:12px;color:var(--warn);margin-top:10px">
    outside training range: ${TRY.outside.map(f => S.esc(f)).join(', ')}. The number is an
    extrapolation.</div>` : '';
  return `<div style="border:1px solid var(--border);border-radius:16px;padding:18px 20px;
      background:var(--surface2)">
    <div class="ptsec" style="margin:0 0 6px;border:0;padding:0">predicted EXECUTION_TIME</div>
    <div style="font-size:44px;font-weight:800;letter-spacing:-.03em;line-height:1.05;
      font-variant-numeric:tabular-nums">${value == null ? '—' : value.toFixed(0)}<span
      style="font-size:20px;color:var(--ink3);font-weight:650"> ms</span></div>
    <div style="margin:12px 0 10px">${verdict}</div>
    <div class="dim" style="font-size:11.8px">model <span class="mono">${S.esc(meta.model_version)}</span>
      · holdout MAPE ${n1(meta.holdout_mape_pct)}% · runs in your browser, model trained on the
      CI runner.</div>${note}</div>`;
}

function paintTry() {
  const root = document.getElementById('try_root');
  if (!root) return;
  if (TRY.status !== 'ready') { root.innerHTML = tryNotice(); return; }
  if (!root.querySelector('#try_form')) {
    root.innerHTML = tryFormHtml();
    root.addEventListener('input', event => {
      const el = event.target.closest('[data-try]');
      if (!el) return;
      const key = el.dataset.try;
      TRY.input[key] = el.type === 'checkbox' ? (el.checked ? 1 : 0) : Number(el.value);
      tryPredict();
    });
  }
  const f = tryFeatures();
  const set = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };
  set('try_v_joins', `<b>${TRY.input.joins}</b>`);
  set('try_v_literal', `<b>${TRY.input.literal}</b>`);
  set('try_derived', `parsed from the text: <b>${f.parsed.n_tables}</b> tables ·
    <b>${fmtRows(f.rows)}</b> rows · <b>${fmtMB(f.bytes)}</b> ·
    <b>${f.parsed.n_predicates}</b> predicate · limit
    <b>${f.parsed.limit_rows || 'none'}</b> · <b>${f.warehouse.threads}</b> threads`);
  set('try_out', tryOutHtml());
  set('try_sql', S.codePanel('the statement the model reads', 'built here, then parsed back',
    f.sql, 'sql', 230));
  set('try_plot', scatterSvg(TRY.ms));
}

window.TRYIT = {
  /* The slide and the tab both drop this in and then call mount(). */
  html() {
    return `<div id="try_root"></div>`;
  },
  mount() {
    if (!document.getElementById('try_root')) return;
    if (TRY.status === 'idle') tryLoad(); else paintTry();
  },
};

window.SLIDES = [
  {id: 'title', kicker: 'MACHINE LEARNING SCENARIO', render() {
    return `<div class="titleslide">
      <div class="kicker">Scenario walkthrough</div>
      <h2>Predict how long a query<br>will run before it runs.</h2>
      <div class="stackchips">
        <span class="schip hot">python</span><span class="schip hot">scikit-learn</span>
        <span class="schip">duckdb</span><span class="schip">onnx</span>
        <span class="schip">github actions</span>
      </div>
      <div class="whw"><span class="whw-k">What</span><span>Teams size warehouses, set timeouts and price jobs on a guess of how long a query will take.</span><span class="whw-k">How</span><span>Time real queries, write them in the shape of <span class="mono">SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY</span>, and learn from the columns that exist before the query starts: the SQL text, the warehouse size, the tables it names.</span><span class="whw-k">Why</span><span>The same columns you already pull from ACCOUNT_USAGE, so the method moves to a real warehouse unchanged. And you can try it yourself on this page.</span></div>
      <div class="byline">${S.esc(S.CFG.author)}</div>
    </div>`;}},

  {id: 'assumptions', kicker: 'ASSUMPTIONS & STRATEGY', render() {
    const s = S.D.summary || {};
    return `<h2>Assumptions &amp; strategy</h2>
      <div class="ptsec">What I assumed</div>
      <ul class="pointlist">
        <li><span class="pt">1</span><span><b>The input is the warehouse's own table.</b>
          Every measured query is a row in the column layout of
          ${m('ACCOUNT_USAGE.QUERY_HISTORY')}, with ${m('ACCOUNT_USAGE.TABLES')} beside it.
          ${s.query_history_columns?.length || 75} columns, filled where we can measure
          them and NULL where a local engine has nothing to say.</span></li>
        <li><span class="pt">2</span><span><b>Only what exists at submit time.</b>
          The parsed ${m('QUERY_TEXT')}, ${m('WAREHOUSE_SIZE')}, the size of the tables named,
          and what the same shape cost before. ${m('BYTES_SCANNED')} and ${m('ROWS_PRODUCED')}
          are the query's own answer and are excluded by construction.</span></li>
        <li><span class="pt">3</span><span><b>The data is measured, not simulated.</b>
          ${S.fmtN(s.queries_measured || 0)} queries on ${s.warehouse_tables || 7} tables,
          the median of ${s.reps_median || 5}+ timed repetitions after a warm-up, on
          ${(s.warehouse_sizes || []).join(', ') || 'three warehouse sizes'}.</span></li>
        <li><span class="pt">4</span><span><b>A shared machine drifts.</b> The same calibration
          query is re-timed every ten queries; each reading is divided by the value interpolated
          to its position. Snowflake has no column for that, so it is published in its own
          table rather than smuggled into one.</span></li>
      </ul>
      <div class="ptsec">How it is built</div>
      <ul class="pointlist">
        <li><span class="pt">1</span><span><b>A standalone solution, not a pipeline.</b> Eight
          Python modules and two entry points: ${m('measure')} → ${m('train')} →
          ${m('predict')} → ${m('publish')}. No warehouse, no orchestrator, no notebook.</span></li>
        <li><span class="pt">2</span><span><b>The gate is fixed before the numbers are known.</b>
          ${m(S.esc(s.gate_rule || 'holdout MAPE ≤ 15% and R² ≥ 0.90'))}. A model that misses it
          is published anyway, marked FAIL here and in ${m('model_versions.csv')}.</span></li>
        <li><span class="pt">3</span><span><b>The interval is reported, not hidden.</b> 2,000
          bootstrap draws over the holdout errors give the 95% CI printed beside every
          MAPE.</span></li>
        <li><span class="pt">4</span><span><b>Retraining is part of the run.</b> Every run
          measures, refits on everything measured so far, and republishes the model and its
          card. ${s.models_trained || 0} versions so far.</span></li>
        <li><span class="pt">5</span><span><b>The tests do not measure anything.</b> The suite
          runs on synthetic rows in seconds, then one smoke test does the real thing on a short
          batch.</span></li>
      </ul>`;}},

  {id: 'input', kicker: 'THE INPUT', render() {
    const s = S.D.summary || {};
    const map = s.feature_map || [];
    const columns = s.query_history_columns || [];
    const after = s.after_the_fact_columns || [];
    const badge = used => used === 'yes' ? S.badge('used', 'b-new', S.ICO.check)
      : used === 'target' ? S.badge('target', 'b-crm') : S.badge('no', 'b-dup');
    const rows = map.map(r => `<tr${r.used === 'no' ? ' class="rowdup"' : ''}>
      <td class="mono" style="white-space:normal;width:37%">${S.esc(r.column)}</td>
      <td style="white-space:normal">${badge(r.used)}
        <span style="margin-left:8px;color:var(--ink2)">${S.esc(r.why)}</span></td></tr>`).join('');
    return `<h2>The input is Snowflake's shape</h2>
      <p class="lead">Every measured query is written as a row of
        ${m('SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY')} — ${columns.length} columns, in order,
        with ${m('ACCOUNT_USAGE.TABLES')} beside it for ${m('ROW_COUNT')} and ${m('BYTES')}.
        ${after.length} of those columns are written by the engine after the query
        finishes, so the feature builder is handed a projection of the other
        ${columns.length - after.length} and cannot read them at all.</p>
      <div style="display:grid;grid-template-columns:${S.isNarrow() ? '1fr' : 'minmax(0,1.5fr) minmax(240px,.62fr)'};gap:26px;align-items:start">
        <div class="verdicts scrollbox"><table style="table-layout:fixed">
          <thead><tr><th>Column</th><th>Used? Why</th></tr></thead>
          <tbody>${rows}</tbody></table></div>
        <div>
          <div class="ptsec" style="margin:0 0 8px">What the model sees</div>
          <div style="display:flex;gap:7px;flex-wrap:wrap">
            ${(s.model_features || []).map(f => `<span class="schip">${S.esc(f)}</span>`).join('')}
          </div>
          <div class="dim" style="font-size:12px;margin-top:14px">
            Thirteen numbers, all of them readable off the statement, the warehouse and the
            catalogue. ${m('features.featurise')} projects each row down to
            ${m('QUERY_TEXT')} and ${m('WAREHOUSE_SIZE')} before it builds anything, and a
            test blanks every after-the-fact column to prove not one feature moves.</div>
        </div>
      </div>`;}},

  {id: 'arch', kicker: 'THE ARCHITECTURE', render() {
    return `<h2>The architecture</h2>
      <p class="lead">Run dispatches a GitHub Actions workflow. Python times the next batch of
        queries on DuckDB and writes them as QUERY_HISTORY rows, scikit-learn refits on
        everything measured so far, and the tables, the model card and the ONNX model are
        committed back to the repository. The page reads what the run wrote.</p>
      <div class="diagram" style="position:relative">
        ${S.isNarrow() ? S.archFlow() : S.svgArch()}
        ${S.isNarrow() ? '' : `<button class="zoombtn" id="archZoomBtn">${S.archZoom ? '&#8854; full picture' : '&#8853; zoom to pipeline'}</button>`}
      </div>`;}},

  {id: 'code', kicker: 'THE CODE', render() {
    const files = S.D.models?.files || [];
    const lines = files.reduce((a, f) => a + f.sql.split('\n').length, 0);
    return `<h2>The code</h2>
      <p class="lead">${files.length} files, ~${Math.round(lines / 10) * 10} lines.
        ${m('snowflake.py')} holds the column layout, ${m('parse.py')} reads a query's shape
        out of its text, ${m('measure.py')} times the batch and divides out the drift,
        ${m('train.py')} fits, scores and gates. Beside them,
        ${m('docs/data_dictionary.md')} says of all
        ${(S.D.summary?.query_history_columns || []).length} columns whether the value is
        measured, derived, estimated or NULL.</p>
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
        <span class="pill">R² <b>${n2(s.holdout_r2)}</b> <span class="dim">log10 ms</span></span>
        <span class="pill">MAE <b>${msLabel(s.holdout_mae_ms)}</b></span>
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
    const versions = S.D.tables.model_versions || [];
    const first = versions[0] || {}, last = versions[versions.length - 1] || {};
    const pane = (title, body) => `<div><div class="ptsec" style="margin:0 0 8px">${title}</div>
      <div style="overflow-x:auto">${body}</div></div>`;
    return `<h2>Why the signal is strong</h2>
      <p class="lead">Runtime is not a preference, it is physics: bytes read, rows hashed, rows
        sorted, threads to do it with. Permutation importance agrees with the query plan: how
        much of the table the filter constant keeps, how much data the statement names, and how
        many threads the warehouse gives it. Retraining on every new batch moved the holdout
        error from
        ${n1(first.holdout_mape_pct)}% to ${n1(last.holdout_mape_pct)}%, against an OLS baseline
        on the same features that stayed near ${n1(s.baseline_mape_pct)}%.</p>
      <div style="display:grid;grid-template-columns:${S.isNarrow() ? '1fr' : '1fr 1fr'};gap:28px;align-items:start">
        ${pane('Permutation importance · holdout · log ms', importanceSvg())}
        ${pane('Holdout MAPE per model version', learningSvg())}
      </div>`;}},

  {id: 'sla', kicker: 'WHAT IT IS FOR', render() {
    const s = S.D.summary || {};
    const all = S.D.tables.sla || [];
    const rank = {missed_breach: 0, false_alarm: 1, breach_called: 2, inside_sla: 3};
    const rows = all.slice().sort((a, b) => rank[a.sla_verdict] - rank[b.sla_verdict]
      || b.worst_actual_ms - a.worst_actual_ms).slice(0, 11);
    const cls = {missed_breach: 'rowdup', false_alarm: 'rowimp'};
    const verdict = {missed_breach: ['missed breach', 'b-dup'], false_alarm: ['false alarm', 'b-dup'],
      breach_called: ['breach called', 'b-new'], inside_sla: ['inside SLA', 'b-crm']};
    return `<h2>What this is for</h2>
      <p class="lead">Admission control, warehouse sizing and cost. Before the query runs the model
        says whether the shape breaches the ${s.sla_ms || 200} ms SLA. Over ${all.length} shapes it
        called ${s.sla_breaches_called || 0} breaches correctly and missed
        ${s.sla_missed_breaches || 0}. A missed breach is a page at 3am; a false alarm is a
        warehouse sized too big. The rows that got it wrong are first.</p>
      <div class="verdicts scrollbox"><table>
        <thead><tr><th>Shape</th><th>Predicted p50</th><th>Measured p50</th><th>Worst measured</th>
          <th>Verdict</th></tr></thead>
        <tbody>${rows.map(r => `<tr${cls[r.sla_verdict] ? ` class="${cls[r.sla_verdict]}"` : ''}>
          <td>${S.esc(r.template_label)}</td>
          <td class="num mono">${msLabel(r.p50_predicted_ms)}</td>
          <td class="num mono">${msLabel(r.p50_actual_ms)}</td>
          <td class="num mono">${msLabel(r.worst_actual_ms)}</td>
          <td>${S.badge(verdict[r.sla_verdict][0], verdict[r.sla_verdict][1])}</td>
        </tr>`).join('')}</tbody></table></div>`;}},

  {id: 'tryit', kicker: 'TRY IT', render() {
    return `<h2>Try it</h2>
      <p class="lead">Set a warehouse size and a query shape. The widget writes the SQL, reads it
        back with the same eight structural questions ${m('parse.py')} asks, and the model published
        by the last run scores it in your browser before anything is executed. Ringed point on the
        diagonal is your query.</p>
      ${window.TRYIT.html()}`;},
    after() { window.TRYIT.mount(); }},
];

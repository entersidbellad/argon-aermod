'use strict';
// Read-only dashboard. Every number is fetched from server.py, which reads it from files on disk.

// --- helpers -----------------------------------------------------------------------
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g,
    c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const isNum = x => x !== null && x !== undefined && Number.isFinite(Number(x));
const fmt = n => isNum(n) ? Number(n).toLocaleString('en-US') : '–';
const usd = x => isNum(x) ? `$${Number(x).toFixed(2)}` : '–';
const fixed = (x, d) => isNum(x) ? Number(x).toFixed(d) : '–';
const short = n => !isNum(n) ? '–' : n >= 1e6 ? `${+(n / 1e6).toFixed(2)}M` : n >= 1e4 ? `${Math.round(n / 1e3)}K`
    : n >= 1e3 ? `${+(n / 1e3).toFixed(1)}K` : String(n);
const pct = x => `${+(100 * x).toFixed(3)}%`;
const tip = text => `<span class="tip" tabindex="0" data-tip="${esc(text)}">i</span>`;
// Status is never colour alone: every status colour comes with its own icon and a text label.
const ICON = {ok: '✓', bad: '✕', warn: '!', prog: '…', neutral: '–'};
const ic = cls => `<span class="ic ${cls}" aria-hidden="true">${ICON[cls] ?? ''}</span>`;
const badge = (cls, text) => `<span class="badge ${cls}">${ic(cls)}${esc(text)}</span>`;
const loading = text => `<div class="loading">${esc(text)}</div>`;
const empty = html => `<div class="empty">${html}</div>`;

async function getJson(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    return r.json();
}

function table(headers, rows) {
    const th = headers.map(h => typeof h === 'string' ? `<th>${h}</th>`
        : `<th class="${h.cls ?? ''}">${h.label}${h.tip ? ' ' + tip(h.tip) : ''}</th>`).join('');
    return `<div class="table-wrap"><table><thead><tr>${th}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
}

// Charts are drawn at their container's pixel width, so chart text matches the page's type scale.
const widthOf = (id, min, max) => Math.max(min, Math.min(max, Math.round($(id).clientWidth) || min));

function niceTicks(max, count = 5) {
    if (!(max > 0)) return [0, 1];
    const raw = max / count, mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
    const ticks = [];
    for (let v = 0; v < max + step * 0.999; v += step) ticks.push(+v.toPrecision(12));
    return ticks;
}

// --- tooltips: one shared bubble for every [data-tip] element, HTML or SVG ------------
const tipEl = $('tooltip');
function showTip(target) {
    tipEl.textContent = target.getAttribute('data-tip');
    tipEl.classList.add('show');
    const r = target.getBoundingClientRect(), w = tipEl.offsetWidth, h = tipEl.offsetHeight;
    const x = Math.max(8, Math.min(window.innerWidth - w - 8, r.left + r.width / 2 - w / 2));
    const y = r.top - h - 8 < 8 ? r.bottom + 8 : r.top - h - 8;
    tipEl.style.left = `${x}px`;
    tipEl.style.top = `${y}px`;
}
const hideTip = () => tipEl.classList.remove('show');
document.addEventListener('mouseover', e => {
    const t = e.target.closest?.('[data-tip]');
    t ? showTip(t) : hideTip();
});
document.addEventListener('focusin', e => {
    const t = e.target.closest?.('[data-tip]');
    t ? showTip(t) : hideTip();
});
document.addEventListener('focusout', hideTip);
window.addEventListener('scroll', hideTip, {passive: true});

// --- shared state: overview (/api/overview) and the frozen rules (/api/frozen) --------
// Refetched with every tab load, so the header, the strip and the tab always agree.
let OVERVIEW = null, FROZEN = null;
async function refreshShared() {
    try {
        [OVERVIEW, FROZEN] = await Promise.all([getJson('/api/overview'), getJson('/api/frozen')]);
    } catch (err) {
        $('chips').innerHTML = `<span class="chip">${ic('bad')}${esc(err.message)}</span>`;
        throw err;
    }
    renderChips();
    renderSteps();
    $('footer-port').innerHTML = OVERVIEW.port_sha256 ? `Python model <code>${esc(OVERVIEW.port_sha256.slice(0, 12))}</code>` : '';
}

// Plain-English explanations of the metrics, with the thresholds read from compare.py.
function glossary() {
    const r = FROZEN.rules, tol = r.slope_tolerance, rel = Number(r.relative_tolerance).toExponential(0);
    return {
        relPct: `${+(r.relative_tolerance * 100).toPrecision(3)}%`,
        slopePct: `${+(tol * 100).toPrecision(3)}%`,
        slope: `Plot every hourly concentration from the port against the reference and fit a line. A perfect port lies on a slope of exactly 1. The EPA rule allows 1 ± ${tol} (${+(tol * 100).toFixed(3)}%) and checks all three definitions EPA's kit uses: through the origin, ordinary least squares, and the ratio of the means.`,
        zero: `Share of paired hourly values where the port and the reference agree on whether there is any concentration at all (whether the plume reached the receptor). Must be at least ${pct(r.zero_agreement_min)}.`,
        p99: `Relative error |port − reference| / reference at the ${r.percentile}th percentile, over every value at least ${+(r.significant_fraction * 100).toFixed(2)}% of the case maximum. Must be ≤ ${rel}. 0 means the numbers are identical.`,
        h4h: `H4H is the "high fourth-high": at each receptor, the 4th-highest daily maximum 1-hour concentration in a year (the highest, for records under about 100 days). It is the design value regulators compare with the 1-hour standard. Every receptor must match within ${rel} relative; the count shows receptors that do not.`,
        epa: `The EPA rule: best-fit slope within 1 ± ${tol}, against EPA's own shipped output when the case has one, otherwise against our gfortran build.`,
        strict: `The strict rule: always against our gfortran build of the same Fortran. Every row present, zero/nonzero agreement ≥ ${pct(r.zero_agreement_min)}, p99 relative error ≤ ${rel}, and every receptor's H4H within ${rel}.`,
        holdout: 'Never shown to the repair loop, so passing it is evidence the port generalises rather than being tuned to the training cases.',
        billed: 'Tokens Argon billed as input. Long replies are decoded in hops and each hop re-reads the prompt and the output so far, so billed input can be several times the prompt (see results/tier_A.md).',
        frozen: 'harness/compare.py decides pass or fail. Its sha256 is pinned in harness/compare.sha256 and checked in CI, so the rules cannot be loosened after seeing results.',
        provenance: 'split.py --verify checks that every file in port/aermod_py is byte-identical to what splitting a saved Argon reply produces, and that the reply belongs to a completed, recorded interaction. A hand edit breaks the trace.',
    };
}

const tierCount = t => {
    const n = t.training.cases.length + t.holdout.cases.length;
    return {passing: t.training.passing + t.holdout.passing, total: n,
            scored: t.training.scored + t.holdout.scored};
};

const certifiedScope = o => o.certified_tiers.length ? `Tier ${o.certified_tiers.join(' + ')}` : '';

function renderChips() {
    const o = OVERVIEW, a = tierCount(o.tiers.A), b = tierCount(o.tiers.B);
    const chips = [];
    const chip = (cls, text, why) => chips.push(`<span class="chip"${why ? ` data-tip="${esc(why)}"` : ''}>${ic(cls)}${esc(text)}</span>`);
    const aStatus = o.tiers.A.status;
    chip(aStatus === 'passing' ? 'ok' : aStatus === 'failing' ? 'bad' : 'neutral',
         aStatus === 'not_scored' ? 'Tier A: not scored' : `Tier A: ${a.passing}/${a.total} EPA cases match`,
         `Tier A (one stack, no building downwash): ${o.tiers.A.training.passing}/${o.tiers.A.training.cases.length} training cases and ${o.tiers.A.holdout.passing}/${o.tiers.A.holdout.cases.length} holdout, from ${o.scores.source ?? 'no scores yet'}.`);
    chip(o.tiers.B.status === 'passing' ? 'ok' : 'prog',
         o.tiers.B.status === 'passing' ? `Tier B: ${b.passing}/${b.total} EPA cases match` : 'Tier B: in progress',
         o.tiers.B.status === 'passing' ? 'Tier B adds PRIME building downwash.'
             : 'Tier B adds PRIME building downwash. It is being ported now; no Tier B result is claimed until its cases pass.');
    const p = o.provenance;
    chip(p.python_files && p.ok ? 'ok' : p.python_files ? 'bad' : 'neutral',
         !p.python_files ? 'No model yet' : p.ok ? 'Provenance verified' : 'Provenance broken',
         `${p.python_files} Python files, traced to ${p.interactions} Argon interaction(s) by split.py --verify.`);
    chip(o.certified ? 'ok' : 'bad',
         o.certified ? `Certified: ${certifiedScope(o)}` : o.scores.suite_found ? 'Not certified' : 'Not yet certified here',
         o.certified ? 'Every certification criterion holds now (Certification tab).'
             : o.scores.suite_found ? 'Some certification criterion fails: see the Certification tab.'
                 : 'Certification needs the model scored on this machine: run make ref refs suite-tier-a, then reload.');
    $('chips').innerHTML = chips.join('');
}

function renderSteps() {
    const o = OVERVIEW, a = tierCount(o.tiers.A), b = tierCount(o.tiers.B), tier = o.tiers.B.status === 'passing' ? 'B' : 'A';
    const tok = o.tokens[tier], p = o.provenance, g = o.argon;
    const values = [
        [tok ? 'ok' : 'neutral', tok ? `Tier ${tier} slice: <b>${fmt(tok.units)}</b> routines, <b>${short(tok.tokens_code_only)}</b> tokens` : 'run python pack.py'],
        [g.interactions ? 'ok' : 'neutral', g.interactions ? `<b>${g.interactions}</b> requests, <b>${usd(g.cost_usd)}</b>${g.cost_complete ? '' : ' (partial)'}` : 'no runs recorded yet'],
        [p.python_files ? (p.ok ? 'ok' : 'bad') : 'neutral', p.python_files ? `<b>${p.python_files}</b> files, ${p.ok ? 'all traced to Argon' : '<b>untraced files</b>'}` : 'no model yet'],
        [o.tiers.A.status === 'passing' ? 'ok' : o.tiers.A.status === 'failing' ? 'bad' : 'neutral',
         o.tiers.A.status === 'not_scored' ? 'not scored yet'
             : `Tier A <b>${a.passing}/${a.total}</b> · Tier B ${o.tiers.B.status === 'passing' ? `<b>${b.passing}/${b.total}</b>` : 'in progress'}`],
        [o.certified ? 'ok' : 'bad', o.certified ? `<b>Yes</b>: ${certifiedScope(o)}` : o.scores.suite_found ? '<b>No</b>: see Certification' : '<b>Not yet</b>: score on this machine'],
    ];
    document.querySelectorAll('#steps .step').forEach((el, i) => {
        const [cls, html] = values[i];
        el.querySelector('.n .ic').outerHTML = ic(cls);
        el.querySelector('.v').innerHTML = html;
    });
}

// --- Port ------------------------------------------------------------------------
async function loadPort() {
    await refreshShared();
    const [runs, snapshots, tokens] = await Promise.all([getJson('/api/runs'), getJson('/api/results'), getJson('/api/tokens')]);
    const G = glossary(), o = OVERVIEW.argon;
    const all = runs.flatMap(r => r.interactions);
    $('spend').innerHTML = [
        ['', 'Argon interactions', fmt(o.interactions), `across ${runs.length} run${runs.length === 1 ? '' : 's'} in agent/runs/`],
        [G.billed, 'Billed input tokens', fmt(o.usage.total_input_tokens), 'what Argon charged as input'],
        ['', 'Output + thinking tokens', fmt(o.usage.total_output_tokens + o.usage.total_thought_tokens),
         `${fmt(o.usage.total_output_tokens)} output, ${fmt(o.usage.total_thought_tokens)} thinking`],
        ['Sum of the per-interaction costs in results/tier_*.md.', 'Total spend',
         o.cost_usd === null ? 'not recorded' : `${usd(o.cost_usd)}${o.cost_complete ? '' : ' (partial)'}`,
         o.prices.length ? `priced in ${o.prices.map(p => p.path).join(', ')}` : 'no price table yet'],
    ].map(([t, k, v, d]) => `<div class="kpi"><div class="k">${esc(k)}${t ? ' ' + tip(t) : ''}</div><div class="v">${v}</div><div class="d">${esc(d)}</div></div>`).join('');

    const calls = Object.fromEntries(snapshots.flatMap(s => s.calls).map(c => [c.interaction_id, c]));
    $('token-chart').innerHTML = all.length === 0
        ? empty('<b>No Argon interactions recorded yet.</b> Run <code>python agent/port.py --tier A</code>, then reload.')
        : tokenChart(runs, calls, widthOf('token-chart', 480, 1100));

    const tiers = ['A', 'B'].filter(t => tokens[t]);
    $('token-method').textContent = tiers.length ? tokens[tiers[0]].method : '';
    $('token-table').innerHTML = tiers.length === 0
        ? empty('<b>context/tokens.json is missing.</b> Run <code>python pack.py</code>.')
        : table(['Tier', {label: 'Units', cls: 'num', tip: 'Fortran program units (subroutines, functions, modules) packed into the prompt.'},
                 {label: 'Lines', cls: 'num'},
                 {label: 'Tokens', cls: 'num', tip: 'Comment-stripped Fortran. agent/port.py sends this by default.'},
                 {label: 'With comments', cls: 'num'}],
            tiers.map(t => `<tr><td><b>Tier ${t}</b><br><span class="muted xsmall">${t === 'A' ? 'no downwash' : 'adds PRIME'}</span></td>
                <td class="num">${fmt(tokens[t].units)}</td><td class="num">${fmt(tokens[t].lines)}</td>
                <td class="num">${fmt(tokens[t].tokens_code_only)}</td><td class="num">${fmt(tokens[t].tokens_with_comments)}</td></tr>`));
    const counted = runs.find(r => r.token_method && r.prompt_tokens);
    $('token-note').innerHTML = (tiers.length ? `Counted with ${esc(tokens[tiers[0]].method)}, a stand-in for Gemini's tokenizer. Prompts add the port contract, the glue, the setup table and the debug catalogue. ` : '')
        + (counted ? `Gemini's own count for run <code>${esc(counted.id)}</code>'s prompt: <b>${fmt(counted.prompt_tokens)}</b> tokens (${esc(counted.token_method)}).` : '');

    $('prices').innerHTML = snapshots.filter(s => s.prices)
        .map(s => `Costs from <code>${esc(s.path)}</code>. Prices: ${esc(s.prices)}`).join('<br>');
    $('runs').innerHTML = runs.length === 0
        ? empty('<b>No runs recorded yet.</b> <code>agent/port.py</code> and <code>agent/repair_loop.py</code> write them under <code>agent/runs/</code>.')
        : table(['Run', 'Kind', 'Tier', 'Model / thinking', {label: 'Interactions', cls: 'num'}, {label: 'Prompt tokens', cls: 'num'},
                 {label: 'Billed input', cls: 'num', tip: G.billed}, {label: 'Output + thinking', cls: 'num'}, {label: 'Cost', cls: 'num'}, 'Outcome'],
            runs.map(r => `<tr class="clickable" data-run="${esc(r.id)}" tabindex="0">
                <td class="mono nowrap">${esc(r.id)}</td><td>${esc(r.kind ?? '–')}</td><td>${esc(r.tier ?? '–')}</td>
                <td>${esc(r.model ?? 'not recorded')}${r.thinking ? ` / ${esc(r.thinking)}` : ''}</td><td class="num">${r.replies}</td>
                <td class="num">${fmt(r.prompt_tokens)}</td>
                <td class="num">${fmt(r.usage.total_input_tokens)}${r.prompt_tokens && r.usage.total_input_tokens > 1.05 * r.prompt_tokens
                    ? `<br><span class="badge warn" data-tip="${esc(G.billed)}">${(r.usage.total_input_tokens / r.prompt_tokens).toFixed(1)}× prompt</span>` : ''}</td>
                <td class="num">${fmt(r.usage.total_output_tokens + r.usage.total_thought_tokens)}</td>
                <td class="num">${usd(r.cost_usd)}</td>
                <td>${outcome(r)}</td>
            </tr>`));
    document.querySelectorAll('tr[data-run]').forEach(tr => {
        tr.onclick = () => showRun(tr.dataset.run);
        tr.onkeydown = e => { if (e.key === 'Enter') showRun(tr.dataset.run); };
    });

    const commits = await getJson('/api/commits?limit=20');
    $('commits').innerHTML = commits.length === 0
        ? empty('No git history for <code>port/aermod_py</code> in this checkout.')
        : `<ul class="commits">${commits.map(c => `<li><code>${esc(c.hash)}</code><span class="muted">${esc(c.date.slice(0, 10))}</span><span>${esc(c.subject)}</span></li>`).join('')}</ul>`;
}

const TOKEN_SERIES = [
    ['prompt', 'Prompt sent', '#2f5f8a'],
    ['billed', 'Billed input', '#a9bccf'],
    ['output', 'Output', '#3f4650'],
    ['thinking', 'Thinking', '#b7bec7'],
];

function tokenChart(runs, calls, W) {
    const groups = runs.flatMap(r => r.interactions.map(i => {
        const call = calls[i.id];
        return {
            title: call?.step ?? `${r.id} (${i.step ?? r.kind ?? 'interaction'})`,
            values: {
                prompt: call?.packet_tokens ?? (r.interactions.length === 1 ? r.prompt_tokens : null),
                billed: i.usage.total_input_tokens, output: i.usage.total_output_tokens, thinking: i.usage.total_thought_tokens,
            },
        };
    }));
    const left = 104, right = 70, barH = 15, gap = 4, groupGap = 18, titleH = 18, top = 6, axisH = 40;
    const rowsPer = TOKEN_SERIES.length;
    const groupH = titleH + rowsPer * (barH + gap);
    const H = top + groups.length * groupH + (groups.length - 1) * groupGap + axisH;
    const vmax = Math.max(1, ...groups.flatMap(g => Object.values(g.values).filter(isNum)));
    const ticks = niceTicks(vmax), dmax = ticks[ticks.length - 1];
    const x = v => left + (W - left - right) * v / dmax;
    const plotBottom = H - axisH + 4;
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Tokens per Argon interaction">`;
    ticks.forEach(t => {
        s += `<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="${top}" y2="${plotBottom}"/>`;
        s += `<text x="${x(t)}" y="${plotBottom + 15}" text-anchor="middle" font-size="11">${short(t)}</text>`;
    });
    s += `<line class="tick" x1="${left}" x2="${W - right}" y1="${plotBottom}" y2="${plotBottom}"/>`;
    s += `<text class="axis-title" x="${left + (W - left - right) / 2}" y="${H - 4}" text-anchor="middle">tokens per interaction</text>`;
    groups.forEach((g, gi) => {
        const y0 = top + gi * (groupH + groupGap);
        s += `<text class="title" x="0" y="${y0 + 12}">${esc(g.title.length > 80 ? g.title.slice(0, 78) + '…' : g.title)}</text>`;
        TOKEN_SERIES.forEach(([key, label, color], ri) => {
            const y = y0 + titleH + ri * (barH + gap), v = g.values[key];
            s += `<text x="${left - 8}" y="${y + barH - 3}" text-anchor="end" font-size="12">${label}</text>`;
            if (!isNum(v)) {
                s += `<text x="${left + 4}" y="${y + barH - 3}" font-size="11" fill="#64748a">not recorded</text>`;
                return;
            }
            s += `<rect x="${left}" y="${y}" width="${Math.max(1, x(v) - left)}" height="${barH}" rx="2" fill="${color}" data-tip="${esc(`${g.title}: ${label.toLowerCase()} ${fmt(v)} tokens`)}"/>`;
            s += `<text x="${x(v) + 5}" y="${y + barH - 3}" font-size="11">${fmt(v)}</text>`;
        });
    });
    return `<div class="legend">${TOKEN_SERIES.map(([, label, c]) => `<span><i style="background:${c}"></i>${label}</span>`).join('')}</div>` + s + '</svg>';
}

function outcome(r) {
    if (r.kind === 'repair') {
        const parts = [`${fmt(r.iterations)} iteration(s)`, `${fmt(r.patches_kept ?? 0)} patch(es) kept`];
        if (r.cases_scored) parts.push(`${r.cases_passing}/${r.cases_scored} training cases pass`);
        if (r.stop_reason) parts.push(esc(r.stop_reason));
        return parts.join('; ');
    }
    const files = new Set(r.interactions.flatMap(i => i.files));
    return [files.size ? `${files.size} files written` : '', esc(r.fortran_pack ?? '')].filter(Boolean).join('; ') || '–';
}

async function showRun(id) {
    document.querySelectorAll('tr[data-run]').forEach(tr => tr.classList.toggle('selected', tr.dataset.run === id));
    $('run-detail').innerHTML = `<div class="run-detail">${loading('Loading run…')}</div>`;
    const run = await getJson(`/api/runs/${id.split('/').map(encodeURIComponent).join('/')}`);
    $('run-detail').innerHTML = `<div class="run-detail"><h3 style="margin-bottom:6px"><code>${esc(id)}</code></h3>` +
        (run.token_method ? `<p class="muted small" style="margin-bottom:8px">Prompt tokens: ${fmt(run.prompt_tokens)} by ${esc(run.token_method)}</p>` : '') +
        table(['Argon interaction', 'Step', 'Files written', {label: 'Billed input', cls: 'num'}, {label: 'Output', cls: 'num'},
               {label: 'Thinking', cls: 'num'}, {label: 'Seconds', cls: 'num'}, {label: 'Cost', cls: 'num'}, 'Repair decision'],
            run.interactions.map(i => `<tr><td class="mono">${esc(i.id)}<br><span class="muted">${esc(i.status)}, ${esc(i.path)}</span></td>
                <td>${esc(i.step ?? '–')}${i.iteration ? ` ${i.iteration}` : ''}</td>
                <td class="mono">${i.files.map(esc).join(', ') || '–'}</td>
                <td class="num">${fmt(i.usage.total_input_tokens)}</td><td class="num">${fmt(i.usage.total_output_tokens)}</td>
                <td class="num">${fmt(i.usage.total_thought_tokens)}</td><td class="num">${i.seconds ? fmt(Math.round(i.seconds)) : '–'}</td>
                <td class="num">${usd(i.cost_usd)}</td>
                <td>${i.decision ? `${badge(i.decision.accepted ? 'ok' : 'bad', i.decision.accepted ? 'kept' : 'rolled back')} ${esc(i.decision.reason ?? '')}
                    <div class="muted small" style="margin-top:4px">${esc(i.decision.hypothesis ?? '')}</div>` : '–'}</td></tr>`)) + '</div>';
}

// --- Proof -----------------------------------------------------------------------
const TIER_SCOPE = {A: 'no building downwash', B: 'adds PRIME building downwash'};

function caseState(r, tierStatus) {
    if (!r) return tierStatus === 'in_progress' ? ['prog', 'prog', 'in progress'] : ['pending', 'warn', 'not scored'];
    if (r.passes) return ['pass', 'ok', 'pass'];
    return tierStatus === 'in_progress' ? ['prog', 'prog', 'in progress'] : ['fail', 'bad', 'fail'];
}

function caseCard(name, r, info, tierStatus, G) {
    const [cls, bcls, label] = caseState(r, tierStatus);
    const role = info.tier === 'holdout' ? `holdout ${tip(G.holdout)}` : 'training';
    const meta = `${role} · reference: ${esc(info.reference)}${info.notes ? ' ' + tip(info.notes) : ''}`;
    let body;
    const verdict = ok => ok === true ? badge('ok', 'pass') : ok === false ? badge(cls === 'prog' ? 'neutral' : 'bad', 'fail')
        : badge('neutral', 'not recorded');
    if (!r) {
        body = `<p class="muted small">${tierStatus === 'in_progress' ? 'Not scored yet: Tier B is being ported.' : 'Not scored: run <code>make suite-tier-a</code>.'}</p>`;
    } else if (r.error) {
        body = `<pre>${esc(r.error.trim().split('\n').slice(-2).join('\n'))}</pre>`;
    } else if (isNum(r.slope)) {
        const slopes = `origin ${fixed(r.slope, 6)}, OLS ${fixed(r.slope_ols, 6)}, mean ratio ${fixed(r.mean_ratio, 6)}`;
        const p99 = !isNum(r.p99_rel_err) ? '–' : Number(r.p99_rel_err) === 0 ? '0 (exact)' : Number(r.p99_rel_err).toExponential(2);
        const neutralFail = cls === 'prog' ? 'neutral' : 'bad';
        const mark = ok => ok === true ? ic('ok') : ok === false ? ic(neutralFail) : ic('neutral');
        const [fails, receptors] = String(r.h4h_fails ?? '').split('/').map(Number);
        const exact = Number(r.p99_rel_err) === 0;
        const plain = [
            [r.strict_pass, exact && r.strict_pass ? 'Hour-by-hour concentrations identical to the Fortran'
                : r.strict_pass ? `Hour-by-hour concentrations within ${G.relPct} of the Fortran` : 'Hour-by-hour concentrations differ from the Fortran'],
            Number.isFinite(receptors) && receptors > 0
                ? [fails === 0, fails === 0 ? `Design value matches at all ${fmt(receptors)} receptors` : `Design value differs at ${fmt(fails)} of ${fmt(receptors)} receptors`]
                : null,
            [r.epa_pass, r.epa_pass ? `Overall agreement within ±${G.slopePct} (EPA rule)` : r.epa_pass === false ? `Overall agreement outside ±${G.slopePct} (EPA rule)` : 'EPA rule not recorded'],
        ].filter(Boolean);
        body = `<ul class="plain">${plain.map(([ok, text]) => `<li>${mark(ok)}<span>${esc(text)}</span></li>`).join('')}</ul>
        <details class="tech"><summary>Technical detail</summary><div class="body"><dl>
            <dt>EPA rule ${tip(G.epa)}</dt><dd>${verdict(r.epa_pass)}</dd>
            <dt>&nbsp; Best-fit slope ${tip(G.slope)}</dt><dd data-tip="${esc(slopes)}">${fixed(r.slope, 6)}</dd>
            <dt>Strict rule ${tip(G.strict)}</dt><dd>${verdict(r.strict_pass)}</dd>
            <dt>&nbsp; Zero/nonzero agreement ${tip(G.zero)}</dt><dd>${isNum(r.zero_agreement) ? `${(100 * r.zero_agreement).toFixed(3)}%` : '–'}</dd>
            <dt>&nbsp; p99 relative error ${tip(G.p99)}</dt><dd>${p99}</dd>
            <dt>&nbsp; H4H receptors failing ${tip(G.h4h)}</dt><dd>${esc((r.h4h_fails ?? '–').replace('/', ' / '))}</dd>
        </dl></div></details>`;
    } else {
        body = `<pre style="color:var(--ink-2)">${esc(r.summary ?? '')}</pre>`;
    }
    return `<div class="case ${cls}"><div class="case-head"><b>${esc(name)}</b>${badge(bcls, label)}</div>
        <div class="meta">${meta}</div>${body}</div>`;
}

function slopeChart(rows, tol, W) {
    const left = 150, right = 24, rowH = 24, top = 30, axisH = 44;
    const H = top + rows.length * rowH + axisH;
    const lo = 1 - 4 * tol, hi = 1 + 4 * tol;
    const x = v => left + (W - left - right) * (Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo);
    const kinds = [['slope', 'through origin', 'circle', '#2f5f8a'], ['slope_ols', 'OLS (EPA R script)', 'square', '#1c2127'], ['mean_ratio', 'ratio of means', 'diamond', '#7d9bb8']];
    const plotBottom = top + rows.length * rowH;
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Best-fit slope by case">`;
    s += `<rect x="${x(1 - tol)}" y="${top - 6}" width="${x(1 + tol) - x(1 - tol)}" height="${plotBottom - top + 6}" fill="#e7f4ed" data-tip="Pass band: 1 ± ${tol}"/>`;
    s += `<text x="${x(1)}" y="${top - 12}" text-anchor="middle" font-size="11" fill="#1e7b4f">pass band 1 ± ${tol}</text>`;
    for (let k = -4; k <= 4; k++) {
        const v = 1 + k * tol;
        s += `<line class="grid" x1="${x(v)}" x2="${x(v)}" y1="${top - 6}" y2="${plotBottom}"/>`;
        s += `<text x="${x(v)}" y="${plotBottom + 15}" text-anchor="middle" font-size="11">${v.toFixed(3)}</text>`;
    }
    s += `<line x1="${x(1)}" x2="${x(1)}" y1="${top - 6}" y2="${plotBottom}" stroke="#1e7b4f" stroke-width="1.5"/>`;
    s += `<line class="tick" x1="${left}" x2="${W - right}" y1="${plotBottom}" y2="${plotBottom}"/>`;
    s += `<text class="axis-title" x="${left + (W - left - right) / 2}" y="${H - 6}" text-anchor="middle">best-fit slope of port vs reference (unitless; 1 = identical; values outside the axis are pinned to its edge)</text>`;
    rows.forEach((r, i) => {
        const yc = top + i * rowH + rowH / 2;
        if (i % 2 === 0) s += `<rect x="${left}" y="${yc - rowH / 2}" width="${W - left - right}" height="${rowH}" fill="#f8fafc" opacity=".6"/>`;
        s += `<text x="${left - 10}" y="${yc + 4}" text-anchor="end" font-size="12" style="font-family:var(--mono)"${r.muted ? ' fill="#64748a"' : ''}>${esc(r.name)}</text>`;
        kinds.forEach(([key, label, shape, color], k) => {
            const v = r[key];
            if (!isNum(v)) return;
            const cx = x(v), cy = yc + (k - 1) * 5, off = v < lo || v > hi;
            const fill = r.muted ? '#9fadbd' : color;
            const t = `data-tip="${esc(`${r.name}: ${label} slope ${Number(v).toFixed(6)}${off ? ' (off the axis)' : ''}`)}"`;
            if (shape === 'circle') s += `<circle cx="${cx}" cy="${cy}" r="4.5" fill="${fill}" ${t}/>`;
            else if (shape === 'square') s += `<rect x="${cx - 4}" y="${cy - 4}" width="8" height="8" fill="${fill}" ${t}/>`;
            else s += `<path d="M${cx} ${cy - 5.5}L${cx + 5.5} ${cy}L${cx} ${cy + 5.5}L${cx - 5.5} ${cy}Z" fill="${fill}" ${t}/>`;
            if (off && k === 0) s += `<text x="${v < lo ? cx + 9 : cx - 9}" y="${yc + 4}" text-anchor="${v < lo ? 'start' : 'end'}" font-size="11" fill="#b3261e">${v < lo ? '◀' : '▶'} ${Number(v).toFixed(3)}</text>`;
        });
    });
    const legend = kinds.map(([, label, , c]) => `<span><i style="background:${c};border-radius:50%"></i>${label}</span>`).join('')
        + '<span><i style="background:#9fadbd"></i>Tier B, in progress</span>';
    return `<div class="legend">${legend}</div>${s}</svg>`;
}

async function loadProof() {
    await refreshShared();
    const G = glossary(), r = FROZEN.rules, tol = r.slope_tolerance, rel = Number(r.relative_tolerance).toExponential(0);
    const data = await getJson('/api/test-results');
    const tiers = OVERVIEW.tiers;

    const cnt = t => `${t.passing}/${t.cases.length}`;
    const kpi = (cls, k, v, d, t) => `<div class="kpi ${cls}"><div class="k">${esc(k)}${t ? ' ' + tip(t) : ''}</div><div class="v">${v}</div><div class="d">${d}</div></div>`;
    const tierCls = st => st === 'passing' ? 'ok' : st === 'failing' ? 'bad' : 'prog';
    const val = (cls, text) => `${ic(cls === 'prog' ? 'neutral' : cls)}${text}`;
    $('rates').innerHTML = [
        kpi(tierCls(tiers.A.status), 'Tier A test cases', tiers.A.training.scored ? val(tierCls(tiers.A.status), cnt(tiers.A.training)) : '–', 'one stack, no buildings: match EPA', ''),
        kpi(tierCls(tiers.A.status), 'Tier A holdout', tiers.A.holdout.scored ? val(tierCls(tiers.A.status), cnt(tiers.A.holdout)) : '–', 'unseen during repair: match EPA', G.holdout),
        tiers.B.status === 'passing'
            ? kpi('ok', 'Tier B: building downwash', val('ok', cnt({passing: tiers.B.training.passing + tiers.B.holdout.passing, cases: [...tiers.B.training.cases, ...tiers.B.holdout.cases]})), 'training and holdout match EPA', '')
            : kpi('prog', 'Tier B: building downwash', val('prog', 'In progress'), `${tiers.B.training.cases.length} training + ${tiers.B.holdout.cases.length} holdout case(s) to port`, 'Tier B adds PRIME building downwash and is being ported now. Its results appear here once results/tier_B.md or out/suite_port.json has Tier B passes.'),
        kpi(OVERVIEW.compare_frozen ? 'ok' : 'bad', 'Scoring script', val(OVERVIEW.compare_frozen ? 'ok' : 'bad', OVERVIEW.compare_frozen ? 'Frozen' : 'CHANGED'), 'matches its pinned fingerprint', G.frozen),
    ].join('');

    $('rules-source').innerHTML = 'thresholds read from <code>harness/compare.py</code>';
    $('rules').innerHTML = `
        <div class="rule"><h3>EPA rule ${tip(G.epa)}</h3>
            <div class="against">Against EPA's own published output where the case has one, otherwise our build of the Fortran.</div>
            <ul><li>Across every hour and receptor, the Python model's concentrations agree with EPA's within ±${G.slopePct} overall.</li></ul>
            <details class="tech"><summary>Technical detail</summary><ul class="body tech-list">
                <li>best-fit slope of port vs reference = 1 ± ${tol}</li>
                <li>three slope definitions, all must pass: through origin, OLS, ratio of means</li></ul></details></div>
        <div class="rule"><h3>Strict rule ${tip(G.strict)}</h3>
            <div class="against">Always against our build of the same Fortran, hour by hour, receptor by receptor.</div>
            <ul>
                <li>Every hourly result exists in both models.</li>
                <li>Both agree on where the plume reaches, in at least ${pct(r.zero_agreement_min)} of hours.</li>
                <li>Concentrations match to within ${G.relPct}.</li>
                <li>The regulatory design value matches at every receptor.</li>
            </ul>
            <details class="tech"><summary>Technical detail</summary><ul class="body tech-list">
                <li>no missing (x, y, date, averaging, group) rows</li>
                <li>zero/nonzero agreement ≥ ${r.zero_agreement_min}</li>
                <li>p${r.percentile} of |port − ref| / ref ≤ ${rel}, over values ≥ ${+(r.significant_fraction * 100).toFixed(2)}% of the case maximum</li>
                <li>per-receptor H4H (high fourth-high design value) within ${rel} relative</li></ul></details></div>`;

    const src = $('score-source');
    if (!data.source) {
        src.innerHTML = 'No scores yet: run <code>make suite-tier-a</code>.';
    } else if (data.suite_found) {
        src.innerHTML = `From <code>${esc(data.source)}</code> (${esc(data.suite_time)}). ` +
            (data.hash_matches ? 'Scored with the current compare.py. ' : '<b>Scored with a different compare.py.</b> ') +
            (data.port_matches ? 'Scored the current port.' : '<b>The port changed since it was scored.</b>');
    } else if (data.source.startsWith('results/')) {
        src.innerHTML = `From the committed snapshot <code>${esc(data.source)}</code> (scored ${esc(data.suite_time ?? '?')}), ` +
            (data.hash_matches ? 'with the current compare.py. ' : '<b>with a different compare.py.</b> ') +
            'Run <code>make suite-tier-a</code> to rescore on this machine.';
    } else {
        src.innerHTML = `From <code>${esc(data.source)}</code>, the repair loop's last scoring. Run <code>make suite-tier-a</code> for scores tied to the port version.`;
    }

    const groups = ['A', 'B'].map(t => {
        const names = [...tiers[t].training.cases, ...tiers[t].holdout.cases];
        const st = tiers[t].status, c = tierCount(tiers[t]);
        const pill = st === 'passing' ? badge('ok', `${c.passing}/${c.total} pass`) : st === 'failing' ? badge('bad', `${c.passing}/${c.total} pass`)
            : st === 'in_progress' ? badge('prog', 'in progress') : badge('neutral', 'not scored');
        const note = st === 'in_progress'
            ? (c.scored ? `<p class="muted small" style="margin-bottom:8px">Tier B is in progress. These scores are shown for transparency and are not a Tier B result.</p>`
                : empty(`<b>Tier B is being ported now.</b> Its cases appear here with scores once <code>results/tier_B.md</code> or <code>out/suite_port.json</code> has Tier B passes.`) + '<div style="height:10px"></div>')
            : '';
        return `<div class="tier-head"><h3>Tier ${t}</h3><span class="scope">${TIER_SCOPE[t]}</span>${pill}</div>${note}
            <div class="cases">${names.map(n => caseCard(n, data.results[n], data.cases[n], st, G)).join('')}</div>`;
    });
    $('case-groups').innerHTML = groups.join('');

    const rows = ['A', 'B'].flatMap(t => [...tiers[t].training.cases, ...tiers[t].holdout.cases]
        .filter(n => isNum(data.results[n]?.slope))
        .map(n => ({name: n, ...data.results[n], muted: t === 'B' && tiers.B.status !== 'passing'})));
    $('slope-chart').innerHTML = rows.length ? slopeChart(rows, tol, widthOf('slope-chart', 560, 1300))
        : empty('<b>No slopes recorded yet.</b> The committed snapshot or <code>out/suite_port.json</code> supplies them.');

    $('frozen').innerHTML = `
        <div class="hash"><div class="k">harness/compare.py now</div><div class="mono">${esc(FROZEN.compare_hash)}</div></div>
        <div class="hash"><div class="k">approved (harness/compare.sha256)</div><div class="mono">${esc(FROZEN.approved_hash ?? 'missing')}</div></div>
        <div class="hash" style="display:flex;align-items:center;justify-content:center">${FROZEN.matches ? badge('ok', 'unchanged') : badge('bad', 'CHANGED')}</div>`;

    const prov = await getJson('/api/provenance');
    $('prov-status').innerHTML = prov.files.length === 0
        ? empty('<b>No port yet.</b> <code>port/aermod_py</code> holds only its README.')
        : `${badge(prov.ok ? 'ok' : 'bad', prov.ok ? 'verified' : 'unverified')} ${tip(G.provenance)} <b>${prov.files.length}</b> files from
           <b>${prov.interactions.length}</b> Argon interaction(s), checked now by the same code as <code>split.py --verify</code>.`;
    $('prov-table').innerHTML = prov.files.length === 0 ? '' :
        table(['File', 'Argon interaction', 'Saved reply', 'Step', 'Status'], prov.files.map(f => `<tr>
            <td class="mono">aermod_py/${esc(f.file)}</td><td class="mono">${esc(f.interaction_id ?? '–')}</td>
            <td class="mono">${esc(f.reply ?? '–')}</td><td>${esc(f.step ?? '–')}</td>
            <td>${f.problem ? `${badge('bad', 'untraced')} ${esc(f.problem)}` : badge('ok', 'traced')}</td></tr>`));
}

// --- Decision ----------------------------------------------------------------------
const CRITERIA = {
    suite_found: ['Scores are fresh for this checkout', 'The port was scored on this machine (make suite-tier-a or make suite-port wrote out/suite_port.json), not only read from a committed snapshot.'],
    compare_approved: ['The scoring script is the approved one', 'harness/compare.py matches the sha256 pinned in harness/compare.sha256.'],
    compare_frozen: ['The scores came from that script', 'The suite recorded which compare.py produced it, and it is the current one.'],
    scored_this_port: ['The scores belong to this exact port', 'The Tier A cases were scored with the same package digest port/aermod_py has now.'],
    tier_a_epa: ['Tier A passes the EPA rule', 'Every Tier A training case: all three best-fit slopes within tolerance.'],
    tier_a_strict: ['Tier A passes the strict rule', 'Every Tier A training case matches our reference build row by row, including each receptor\'s H4H design value.'],
    port_exists: ['A port exists', 'port/aermod_py contains generated Python files.'],
    provenance: ['Every file came from Argon', 'Each file traces to a saved, completed Argon interaction; any hand edit breaks the trace.'],
};

async function loadDecision() {
    await refreshShared();
    const data = await getJson('/api/certify');
    const failing = data.criteria.filter(c => !c.ok);
    const needsScoring = failing.length > 0 && failing.every(c => ['suite_found', 'scored_this_port'].includes(c.name));
    const withB = data.certified && OVERVIEW.certified_tiers.includes('B');
    const v = $('verdict');
    v.className = `verdict ${data.certified ? 'ok' : 'bad'}`;
    v.innerHTML = `${ic(data.certified ? 'ok' : 'bad')}<div>
        <h2>${data.certified ? `Certified for ${OVERVIEW.certified_tiers.map(t => `Tier ${t}`).join(' and ')}` : 'Not certified'}</h2>
        <p>${data.certified
            ? `All ${data.criteria.length} criteria hold right now: the frozen script scored this exact model, every Tier A training case passes both rules${withB ? ', every Tier B case passes in the same scoring' : ''}, and every file traces to Argon.`
            : `${failing.length} of ${data.criteria.length} criteria fail: ${failing.map(c => esc((CRITERIA[c.name] ?? [c.name])[0].toLowerCase())).join('; ')}.`
              + (needsScoring ? ' On a fresh checkout this is expected: run <code>make ref refs suite-tier-a</code> to score the port on this machine, then reload.' : '')}</p></div>`;
    $('criteria').innerHTML = data.criteria.map(c => {
        const [title, why] = CRITERIA[c.name] ?? [c.name, ''];
        return `<li><span role="img" aria-label="${c.ok ? 'pass' : 'fail'}">${ic(c.ok ? 'ok' : 'bad')}</span>
            <div><div class="title">${esc(title)}</div><div class="why">${esc(why)}</div></div>
            <div class="detail"><span class="muted">${esc(c.name)}:</span> ${esc(c.detail)}</div></li>`;
    }).join('');
    const b = OVERVIEW.tiers.B;
    $('scope-note').innerHTML = `<h2>What certification covers</h2>
        <p class="small" style="margin-top:8px;color:var(--ink-2)">Tier A: point sources (stacks) on flat, rural terrain, 1-hour averages, no building downwash.
        The holdout cases are reported on the Model verification tab but are not certification criteria, so the repair loop can never be tuned to them.</p>
        <p class="small" style="color:var(--ink-2)">Tier B (PRIME building downwash): ${withB
            ? 'every Tier B case, training and holdout, passes in the same scoring of this exact model, so the certification extends to Tier B.'
            : b.status === 'passing'
                ? 'all its cases pass on the Model verification tab, but not in a scoring of this exact model on this machine; run <code>make suite-port</code> to extend certification to Tier B.'
                : 'in progress. Nothing on this page claims a Tier B result.'}</p>
        <p class="small" style="color:var(--ink-2)">Not ported by design: input parsing and output writing. The human-written <code>harness/glue.py</code>
        builds every setup value the physics reads and is checked bit for bit against an instrumented AERMOD build.</p>`;
}

// --- Fuel & stack check (what-if) -------------------------------------------------------
const WI_SLIDERS = {height: 'stack_height_m', diameter: 'stack_diameter_m',
                    temperature: 'exit_temperature_k', velocity: 'exit_velocity_ms'};
const WI_FMT = {height: v => `${v} m`, diameter: v => `${v} m`,
                temperature: v => `${Math.round(v - 273.15)} °C <small>(${v} K)</small>`, velocity: v => `${v} m/s`};
const LB_PER_HR_PER_G_S = 3600 / 453.59237;
const gs = v => `${fixed(v, 1)} g/s <small>(${fmt(Math.round(v * LB_PER_HR_PER_G_S))} lb/hr)</small>`;
// Amber "near limit" is this dashboard's screening margin, not a regulatory threshold.
const NEAR_LIMIT_PCT = 80;
const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
const compass = deg => COMPASS[Math.round((deg % 360) / 22.5) % 16];
const ug = x => `${Number(x).toLocaleString('en-US', {maximumFractionDigits: x < 10 ? 2 : 1})} µg/m³`;
const ordinal = n => `${n}${n === 1 ? 'st' : n === 2 ? 'nd' : n === 3 ? 'rd' : 'th'}`;
const POL_SHORT = {SO2: 'SO₂', NOX: 'NO₂'};
const polShort = k => POL_SHORT[k] ?? k;
const STD_NAME = {one_hour: '1-hour', annual: 'Annual'};
const levelOf = s => !s.passes ? 'bad' : s.percent_of_limit >= NEAR_LIMIT_PCT ? 'warn' : 'ok';
const LEVEL_TEXT = {ok: 'PASS', warn: 'NEAR LIMIT', bad: 'EXCEEDS'};
let WI = null, wiTimer = null, wiLast = null;

const gridValue = id => WI.grid[WI_SLIDERS[id]][Number($(`wi-${id}`).value)];

async function loadWhatif() {
    const shared = refreshShared();
    if (!WI) {
        WI = await getJson('/api/whatif/config');
        initWhatif();
    }
    await Promise.all([shared, updateWhatif()]);
}

function initWhatif() {
    const far = Math.max(...WI.receptors.distances_m) / 1000;
    $('wi-title').textContent = 'Cement kiln: does a fuel or stack change stay inside the standards?';
    $('wi-story').innerHTML = `A cement plant wants to burn part of its kiln fuel as alternative fuels (tyres, plastics, refuse-derived fuel)
        or change its stack. Pick a fuel mix and stack: the cards compare today's operation with the change, as a percentage of the
        US National Ambient Air Quality Standards (NAAQS). One kiln stack on flat, rural ground, with concentrations at
        ${WI.receptors.directions} directions × ${WI.receptors.distances_m.length} distances out to ${far} km.`;
    $('wi-sources').innerHTML = `
        <div class="source"><span class="lab">Real</span>Dispersion computed by the Argon-ported AERMOD; a full year of hourly weather
            from ${esc(WI.met.label)}; NAAQS limits from 40 CFR part 50.</div>
        <div class="source illus"><span class="lab">Illustrative</span>Fuel-mix factors, emission rates, stack defaults and background
            concentrations are example values, not plant data. Inputs marked <span class="tag">illustrative</span> come from
            <code>${esc(WI.config_path ?? 'whatif/kiln.toml')}</code>.</div>`;
    $('wi-pollutant').innerHTML = Object.entries(WI.pollutants)
        .map(([k, p]) => `<option value="${esc(k)}">${esc(p.label)}</option>`).join('');
    $('wi-pollutant').value = WI.defaults.pollutant;
    $('wi-fuel').innerHTML = Object.entries(WI.fuel_mix)
        .map(([k, m]) => `<option value="${esc(k)}">${esc(m.label)}</option>`).join('');
    $('wi-fuel').value = WI.defaults.fuel_mix;
    for (const [id, key] of Object.entries(WI_SLIDERS)) {
        const el = $(`wi-${id}`);
        el.min = 0; el.max = WI.grid[key].length - 1; el.step = 1;
        el.value = Math.max(0, WI.grid[key].indexOf(WI.defaults[key]));
    }
    $('wi-key').innerHTML = `<span><i class="bg"></i>background already in the air (illustrative)</span>
        <span>${ic('ok')}kiln adds, total within ${NEAR_LIMIT_PCT}% of the standard</span>
        <span>${ic('warn')}near limit: ${NEAR_LIMIT_PCT}–100%</span>
        <span>${ic('bad')}exceeds the standard</span>
        <span><i class="std"></i>NAAQS</span><span><i class="near"></i>${NEAR_LIMIT_PCT}% of NAAQS</span>`;
    applyPollutant();
    $('wi-pollutant').onchange = () => { applyPollutant(); scheduleWhatif(); };
    $('wi-fuel').onchange = () => { applyPreset(); scheduleWhatif(); };
    $('wi-bldg').onchange = () => { $('wi-bldg-box').style.display = $('wi-bldg').checked ? 'block' : 'none'; scheduleWhatif(); };
    $('wi-metric').onchange = () => wiLast && renderMaps(wiLast);
    for (const id of ['height', 'diameter', 'temperature', 'velocity', 'emission', 'bg1', 'bgA', 'bh', 'bw', 'bd', 'urban', 'terrain']) {
        $(`wi-${id}`).addEventListener('input', scheduleWhatif);
    }
}

function applyPreset() {
    const p = WI.presets[$('wi-pollutant').value][$('wi-fuel').value];
    $('wi-emission').value = p.emission_rate_gs;
    $('wi-temperature').value = WI.grid.exit_temperature_k.indexOf(p.exit_temperature_k);
}

function applyPollutant() {
    const pol = WI.pollutants[$('wi-pollutant').value];
    $('wi-emission').min = 0;
    $('wi-emission').max = pol.emission_rate_max_gs;
    $('wi-bg1').value = pol.background_1h_ugm3;
    $('wi-bgA').value = pol.background_annual_ugm3;
    applyPreset();
}

function wiLabels() {
    for (const id of Object.keys(WI_SLIDERS)) $(`wi-${id}-v`).innerHTML = WI_FMT[id](gridValue(id));
    $('wi-emission-v').innerHTML = gs(Number($('wi-emission').value));
    $('wi-bh-v').textContent = `${$('wi-bh').value} m`;
    $('wi-bw-v').textContent = `${$('wi-bw').value} m`;
    $('wi-bd-v').textContent = `${$('wi-bd').value} m`;
}

function scheduleWhatif() {
    wiLabels();
    clearTimeout(wiTimer);
    wiTimer = setTimeout(() => updateWhatif().catch(err => console.error(err)), 120);
}

async function updateWhatif() {
    wiLabels();
    const bldg = $('wi-bldg').checked;
    const q = new URLSearchParams({
        pollutant: $('wi-pollutant').value, height: gridValue('height'), diameter: gridValue('diameter'),
        temperature: gridValue('temperature'), velocity: gridValue('velocity'), emission: $('wi-emission').value,
        background_1h: $('wi-bg1').value || 0, background_annual: $('wi-bgA').value || 0,
        building_height: bldg ? $('wi-bh').value : 0, building_width: bldg ? $('wi-bw').value : 0,
        building_distance: bldg ? $('wi-bd').value : 0,
        urban: $('wi-urban').checked, complex_terrain: $('wi-terrain').checked,
    });
    const data = await getJson(`/api/whatif?${q}`);
    wiLast = data;
    renderVerdicts(data);
    renderMaps(data);
    renderStandards();
    renderArgonNote(data);
}

function stackText(i) {
    const s = i.stack;
    return `${s.height_m} m stack, ${s.diameter_m} m diameter, ${Math.round(s.temperature_k - 273.15)} °C, ${s.velocity_ms} m/s · ` +
        `${fixed(i.emission_rate_gs, 1)} g/s (${fmt(Math.round(i.emission_rate_gs * LB_PER_HR_PER_G_S))} lb/hr)`;
}

function gauge(pol, key, s) {
    const std = WI.naaqs[pol][key], level = levelOf(s);
    const max = Math.max(120, s.percent_of_limit * 1.08);
    const at = pctOfLimit => `${(100 * pctOfLimit / max).toFixed(2)}%`;
    const bgPct = 100 * s.background_ugm3 / s.limit_ugm3;
    const name = `${STD_NAME[key]} ${polShort(pol)}`;
    return `<div class="gauge">
        <div class="gl"><span class="name">${ic(level)}${esc(name)} <span class="muted" style="font-weight:500">${LEVEL_TEXT[level]}</span></span>
            <span class="val"><b>${fixed(s.total_ugm3, 1)}</b> / ${fixed(s.limit_ugm3, 1)} µg/m³ · <b>${s.percent_of_limit.toFixed(0)}%</b></span></div>
        <div class="bar" role="img" aria-label="${esc(`${name}: ${s.percent_of_limit.toFixed(0)}% of the standard, ${LEVEL_TEXT[level]}`)}">
            <div class="seg bg" style="width:${at(bgPct)}" data-tip="${esc(`Background (illustrative): ${ug(s.background_ugm3)}`)}"></div>
            <div class="seg kiln ${level}" style="left:${at(bgPct)};width:${at(Math.max(0, s.percent_of_limit - bgPct))}"
                data-tip="${esc(`Kiln adds ${ug(s.total_ugm3 - s.background_ugm3)}`)}"></div>
            <div class="line near" style="left:${at(NEAR_LIMIT_PCT)}"></div>
            <div class="line" style="left:${at(100)}" data-tip="${esc(`NAAQS ${std.ppb} ppb = ${ug(std.limit_ugm3)}`)}"></div>
        </div>
        <div class="scale"><span style="left:0;transform:none">0</span>${max <= 125 ? `<span style="left:${at(NEAR_LIMIT_PCT)}">${NEAR_LIMIT_PCT}%</span>` : ''}
            <span class="std" style="left:${at(100)}">NAAQS ${std.ppb} ppb</span></div>
    </div>`;
}

function verdictCard(who, what, r, pol) {
    const head = `<div class="vhead"><div class="who">${esc(who)}</div><div class="what">${esc(what)}</div>
        <div class="stack">${esc(stackText(r.inputs))}</div></div>`;
    if (!r.certified) {
        const unavailable = r.status === 'unavailable';
        return `<div class="vcard">${head}<div class="big"><span class="vstatus neutral">${ic('neutral')}${unavailable ? 'NO RESULT' : 'OUTSIDE SCOPE'}</span></div>
            <div class="outscope"><ul>${r.issues.map(i => `<li>${esc(i)}</li>`).join('')}</ul>
            ${unavailable ? '' : '<p style="margin-top:8px">No number is shown. This demo covers one stack on flat, rural terrain with no building close enough to cause downwash.</p>'}</div></div>`;
    }
    const worst = ['one_hour', 'annual'].reduce((a, k) => r[k].percent_of_limit > r[a].percent_of_limit ? k : a, 'one_hour');
    const s = r[worst], level = levelOf(s), m = r.max_1h;
    const allPass = r.one_hour.passes && r.annual.passes;
    return `<div class="vcard ${level}">${head}
        <div class="big"><span class="pctv">${s.percent_of_limit.toFixed(0)}%</span>
            <span class="pctl">of the <b>${STD_NAME[worst]}&nbsp;${polShort(pol)} NAAQS</b><br><span class="muted">limiting standard</span></span>
            <span class="vstatus ${level}" data-tip="${esc(allPass ? (level === 'warn' ? `Within both standards, but at or above ${NEAR_LIMIT_PCT}% of one: little margin for a bad weather year or higher background.` : 'Within both standards.') : 'Above at least one standard.')}">${ic(level)}${LEVEL_TEXT[level]}</span></div>
        <div class="gauges">${gauge(pol, 'one_hour', r.one_hour)}${gauge(pol, 'annual', r.annual)}</div>
        <dl class="facts">
            <dt>Kiln contribution, 1-hour design value</dt><dd>${ug(r.one_hour.total_ugm3 - r.one_hour.background_ugm3)}</dd>
            <dt>Highest single hour, kiln only</dt><dd>${ug(m.value_ugm3)}</dd>
            <dt>Where it lands, from the stack</dt><dd>${(m.distance_m / 1000).toFixed(1)} km ${compass(m.direction_deg)}</dd>
        </dl></div>`;
}

function renderVerdicts(data) {
    const pol = $('wi-pollutant').value;
    $('wi-verdicts').innerHTML =
        verdictCard('Today (baseline)', `${WI.fuel_mix[WI.defaults.fuel_mix].label}, current stack`, data.baseline, pol)
        + verdictCard('Proposed change', WI.fuel_mix[$('wi-fuel').value].label, data.scenario, pol);
    $('wi-verdict-sub').textContent = `Design value at the worst receptor, kiln plus background, as % of the ${polShort(pol)} NAAQS`;
}

const PALETTE = [[244, 245, 247], [208, 219, 230], [160, 184, 207], [103, 140, 176], [47, 95, 138], [22, 50, 77]];
function color(t) {
    t = Math.max(0, Math.min(1, t)) * (PALETTE.length - 1);
    const i = Math.min(Math.floor(t), PALETTE.length - 2), f = t - i;
    const c = PALETTE[i].map((a, k) => Math.round(a + (PALETTE[i + 1][k] - a) * f));
    return `rgb(${c.join(',')})`;
}

function polarMap(title, r, metric, vmax) {
    const S = 360, cx = S / 2, cy = S / 2 + 20, r0 = 14, R = S / 2 - 34;
    const dists = [...WI.receptors.distances_m].sort((a, b) => a - b), n = WI.receptors.directions;
    const w = (R - r0) / dists.length, half = Math.PI / n;
    const pt = (rad, ang) => [cx + rad * Math.sin(ang), cy - rad * Math.cos(ang)];
    let s = `<svg class="chart" viewBox="0 0 ${S} ${S + 44}"><text class="title" x="${cx}" y="14" text-anchor="middle">${esc(title)}</text>`;
    if (!r.certified) {
        const msg = r.status === 'unavailable' ? 'not precomputed' : 'outside the demo scope';
        return s + `<circle cx="${cx}" cy="${cy}" r="${R}" fill="#eceef1" stroke="#c3c8cf"/>
            <text x="${cx}" y="${cy}" text-anchor="middle" font-size="14" fill="#4d5560">${msg}</text></svg>`;
    }
    const vals = r.field[metric];
    r.field.x.forEach((x, i) => {
        const y = r.field.y[i], d = Math.hypot(x, y), ang = Math.atan2(x, y);
        const ring = dists.findIndex(v => Math.abs(v - d) < 1);
        const [ri, ro] = [r0 + ring * w, r0 + (ring + 1) * w];
        const [a, b] = [ang - half, ang + half];
        const p = [pt(ro, a), pt(ro, b), pt(ri, b), pt(ri, a)];
        const where = `${d >= 1000 ? +(d / 1000).toFixed(1) + ' km' : Math.round(d) + ' m'} ${compass((ang * 180 / Math.PI + 360) % 360)}`;
        s += `<path d="M${p[0]} A${ro},${ro} 0 0 1 ${p[1]} L${p[2]} A${ri},${ri} 0 0 0 ${p[3]} Z" fill="${color(vals[i] / vmax)}" stroke="#fff" stroke-width="0.5" data-tip="${esc(`${where}: ${ug(vals[i])}`)}"/>`;
    });
    dists.forEach((d, k) => {
        s += `<text x="${cx + 3}" y="${cy - (r0 + (k + 1) * w) + 10}" font-size="8.5" fill="#1c2127" paint-order="stroke" stroke="#fff" stroke-width="3">${d >= 1000 ? d / 1000 + ' km' : d + ' m'}</text>`;
    });
    const best = vals.indexOf(Math.max(...vals));
    const bx = r.field.x[best], by = r.field.y[best], bd = Math.hypot(bx, by);
    const bring = dists.findIndex(v => Math.abs(v - bd) < 1);
    const [mx, my] = pt(r0 + (bring + 0.5) * w, Math.atan2(bx, by));
    s += `<circle cx="${mx}" cy="${my}" r="7" fill="none" stroke="#fff" stroke-width="4"/>`;
    s += `<circle cx="${mx}" cy="${my}" r="7" fill="none" stroke="#1c2127" stroke-width="2" data-tip="${esc(`Highest: ${ug(vals[best])}`)}"/>`;
    s += `<rect x="${cx - 4}" y="${cy - 4}" width="8" height="8" fill="#1c2127" data-tip="Kiln stack"/>`;
    for (const [lab, ang] of [['N', 0], ['E', 90], ['S', 180], ['W', 270]]) {
        const [tx, ty] = pt(R + 14, ang * Math.PI / 180);
        s += `<text x="${tx}" y="${ty + 4}" font-size="12" font-weight="600" text-anchor="middle" fill="#3f4650">${lab}</text>`;
    }
    s += `<text x="${cx}" y="${S + 38}" font-size="12" text-anchor="middle">highest ${ug(vals[best])} (circled)</text>`;
    return s + '</svg>';
}

function renderMaps(data) {
    const metric = $('wi-metric').value;
    const shown = [data.baseline, data.scenario].filter(r => r.certified);
    const vmax = Math.max(1e-12, ...shown.flatMap(r => r.field[metric]));
    const what = {annual: 'annual mean', one_hour: '1-hour design value', max_1h: 'highest single hour'}[metric];
    const legend = `<svg class="chart" viewBox="0 0 640 40" style="max-width:640px">${[...Array(50).keys()].map(i =>
        `<rect x="${70 + i * 10}" y="4" width="10" height="12" fill="${color(i / 49)}"/>`).join('')}
        <text x="64" y="14" font-size="11" text-anchor="end">0</text><text x="576" y="14" font-size="11">${ug(vmax)}</text>
        <text x="70" y="32" font-size="11" fill="#59606b">kiln contribution only (no background), ${esc(what)}, µg/m³; same scale for both maps</text></svg>`;
    $('wi-maps').innerHTML = polarMap('Today (baseline)', data.baseline, metric, vmax) + polarMap('Proposed change', data.scenario, metric, vmax);
    $('wi-map-note').innerHTML = legend + `<p>Each cell is one receptor (${WI.receptors.directions} directions, rings at
        ${WI.receptors.distances_m.map(d => d >= 1000 ? d / 1000 + ' km' : d + ' m').join(', ')}).
        Rings are drawn evenly spaced, so read distance from the labels. Hover a cell for its value.</p>`;
}

function renderStandards() {
    const pol = $('wi-pollutant').value, std = WI.naaqs[pol], mw = WI.pollutants[pol].molecular_weight;
    const line = (name, s) => `<li><b>${name}: ${s.ppb} ppb = ${s.limit_ugm3.toFixed(1)} µg/m³</b>
        (${esc(s.form)}). ${esc(s.cite)}.</li>`;
    $('wi-standards').innerHTML = `<ul>
        ${line('1-hour', std.one_hour)}${line('Annual', std.annual)}</ul>
        <p>Source: US EPA, <a href="https://www.epa.gov/criteria-air-pollutants/naaqs-table" target="_blank" rel="noopener">NAAQS Table</a>
        (40 CFR part 50). Converted with µg/m³ = ppb × ${mw} / 24.45 (25 °C, 1 atm, 40 CFR 50.3).
        Emission rates convert at 1 g/s = ${LB_PER_HR_PER_G_S.toFixed(2)} lb/hr.</p>
        <ul style="margin-top:8px">
        <li>Design value: the 1-hour standard's form is a percentile of daily maximum 1-hour values averaged over 3 years. With one year of
            weather this demo uses the ${ordinal(std.one_hour.rank)}-highest daily maximum at each receptor (the high-${ordinal(std.one_hour.rank)}-high),
            the single-year stand-in used in EPA modelling practice. The annual standard is compared with the one-year mean.</li>
        <li>% of standard = (kiln design value + background) / NAAQS at the worst receptor. "Near limit" (amber) marks ${NEAR_LIMIT_PCT}% or more:
            a screening margin used by this dashboard, not a regulatory threshold.</li>
        ${pol === 'NOX' ? '<li>All NOx is treated as NO2 (EPA Tier 1 full conversion), which overstates NO2.</li>' : ''}
        <li>Background values are illustrative. A permit study uses monitored background for the site.</li>
        <li>Stack values snap to the ${WI.stacks} precomputed stacks. Emission rate is continuous, because AERMOD's
            concentrations scale exactly with emission rate.</li>
        <li>A real study uses a denser receptor grid, several years of local weather, nearby buildings (downwash) and terrain.
            This demo covers one stack on flat, rural terrain with no nearby buildings, and refuses anything else.</li></ul>`;
}

function renderArgonNote(data) {
    const p = (data.scenario.certified ? data.scenario : data.baseline).provenance;
    const coverage = WI.cached < WI.stacks ? ` <b>Only ${WI.cached} of ${WI.stacks} stacks are precomputed.</b>` : '';
    $('wi-argon').innerHTML = !p ? `No precomputed results.${coverage}` :
        `Computed by the Argon-ported AERMOD (<code>port/aermod_py</code>, version <code>${esc(p.port_sha256.slice(0, 12))}</code>),
        the same Python model scored on the <a href="#proof" onclick="show('proof');return false">Model verification tab</a>. Each stack is ${fmt(p.hours)} hours of weather
        (${fmt(p.excluded_hours)} calm or missing) on ${WI.receptors.directions * WI.receptors.distances_m.length} receptors,
        run once at 1 g/s (${Math.round(p.seconds)} s for this stack) and scaled to the chosen emission rate.` +
        (p.port_is_current ? '' : ` ${badge('bad', 'computed with a different model version: rerun make whatif')}`) + coverage;
}

// --- tabs ----------------------------------------------------------------------------
const loaders = {port: loadPort, proof: loadProof, decision: loadDecision, whatif: loadWhatif};
const loaded = {};
function show(screen) {
    document.querySelectorAll('.tabs button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.screen === screen)));
    document.querySelectorAll('.screen').forEach(s => s.classList.toggle('active', s.id === screen));
    if (location.hash.slice(1) !== screen) history.replaceState(null, '', `#${screen}`);
    loaded[screen] = loaders[screen]().catch(err => {
        console.error(err);
        $(screen).insertAdjacentHTML('afterbegin', `<div class="error"><b>Could not load this tab:</b> ${esc(err.message)}. Is <code>server.py</code> still running?</div>`);
    });
    return loaded[screen];
}
document.querySelectorAll('.tabs button').forEach(b => b.onclick = () => show(b.dataset.screen));
document.querySelectorAll('#steps .step').forEach(b => b.onclick = () => {
    show(b.dataset.go);
    document.querySelector('.tabs').scrollIntoView({behavior: 'smooth', block: 'start'});
});
let resizeTimer = null;
window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
        const screen = document.querySelector('.screen.active')?.id;
        if (screen && screen !== 'decision' && screen !== 'whatif') show(screen);
    }, 250);
});
window.addEventListener('hashchange', () => loaders[location.hash.slice(1)] && show(location.hash.slice(1)));
show(loaders[location.hash.slice(1)] ? location.hash.slice(1) : 'whatif');

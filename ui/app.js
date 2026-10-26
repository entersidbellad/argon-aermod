'use strict';
// Read-only dashboard. Every number is fetched from server.py, which reads it from files on disk,
// or, in the static export (tools/export_static.py), from the JSON it saved from server.py.

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
const tip = text => `<span class="tip" tabindex="0" role="button" aria-label="More information" data-tip="${esc(text)}">i</span>`;
// Status is never colour alone: every status colour comes with its own icon and a text label.
const ICON = {ok: '✓', bad: '✕', warn: '!', prog: '…', neutral: '–'};
const ic = cls => `<span class="ic ${cls}" aria-hidden="true">${ICON[cls] ?? ''}</span>`;
const badge = (cls, text) => `<span class="badge ${cls}">${ic(cls)}${esc(text)}</span>`;
const loading = text => `<div class="loading">${esc(text)}</div>`;
const empty = html => `<div class="empty">${html}</div>`;
const longDate = iso => {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? String(iso ?? '') : d.toLocaleDateString('en-GB', {day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC'});
};

const CONTACT = 'mailto:siddharthbellad2001@gmail.com?subject=' + encodeURIComponent('Kiln Permit Check: run it on our plant');
document.querySelectorAll('[data-contact]').forEach(a => { a.href = CONTACT; });

// Set by data/static.js in the static export; undefined under server.py.
const STATIC = window.AERMOD_STATIC ?? null;
const apiUrl = url => STATIC ? `data/${url.split('?')[0].replace(/^\/api\//, '')}.json` : url;

async function getJson(url) {
    const r = await fetch(apiUrl(url));
    if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    return r.json();
}

const extLink = (href, text) => `<a href="${esc(href)}" target="_blank" rel="noopener">${text}</a>`;
const ciRun = () => STATIC.ci ? extLink(STATIC.ci.run_url, `CI run ${esc(STATIC.ci.run_id)}`) : 'CI';
const ciCommitUrl = () => `${STATIC.ci.run_url.split('/actions/')[0]}/commit/${STATIC.ci.commit}`;

if (STATIC) {
    $('demo-banner').innerHTML = `<div class="demo-banner" role="note"><div class="wrap">
        <span class="demo-dot" aria-hidden="true"></span>
        <span><b>Demo with example plant data</b>. Contact us to run it on your plant.</span>
        <a data-contact href="${esc(CONTACT)}">Get in touch <span aria-hidden="true">→</span></a></div></div>`;
}

// --- plain-English glossary: hover or focus any dotted term -----------------------------
const NEAR_LIMIT_PCT = 80;
const GLOSS = {
    naaqs: ['Federal air-quality limit (NAAQS)', 'The US EPA\'s National Ambient Air Quality Standards: the legal ceiling for each pollutant in the outdoor air people breathe. Permit modelling must show a plant will not push the air above them.'],
    so2: ['SO₂, sulfur dioxide', 'A gas formed when sulfur in the fuel and raw materials burns. It irritates the lungs and has a 1-hour and a yearly federal limit.'],
    nox: ['NOx, nitrogen oxides', 'Gases formed in hot flames, mainly NO and NO₂. This demo counts all of it as NO₂, the regulated gas, which errs on the safe side.'],
    pm10: ['PM10', 'Dust and particles smaller than 10 micrometres, small enough to breathe in. One of EPA\'s test cases models them.'],
    stack: ['Stack', 'The kiln\'s chimney. Its height, width, gas temperature and gas speed decide how high the plume rises before it spreads out.'],
    downwash: ['Building wake (downwash)', 'Wind flowing over a nearby building drags the plume down to the ground sooner, raising concentrations close to the plant. EPA models it with a method called PRIME.'],
    background: ['Background', 'Pollution already in the air from other sources, such as traffic and other plants. It is added to the plant\'s share before comparing with the limit.'],
    worst: ['Worst spot', 'The point around the plant where the air comes closest to the limit. For the 1-hour limit the model uses one of the highest daily peaks of the year rather than the single worst hour, the way EPA defines the limit.'],
    margin: ['Close-to-limit margin', `Results at ${NEAR_LIMIT_PCT}% of a limit or more are flagged as close. It is a screening margin chosen for this tool, not a regulation: it leaves room for a worse weather year or higher background.`],
    aermod: ['AERMOD', 'The air-dispersion model the US EPA requires for permit modelling of industrial sources (40 CFR Part 51, Appendix W). EPA publishes it as Fortran source code.'],
    ci: ['Automatic check (CI)', 'An independent build server reruns every EPA test case whenever the code changes and records the result publicly. CI stands for continuous integration.'],
    holdout: ['Held-back test case', 'Kept out of development entirely. Passing it shows the model was not tuned to the tests it was built against.'],
    ugm3: ['µg/m³', 'Micrograms of pollutant per cubic metre of air: how limits and model results are measured.'],
};
const term = (key, text) => `<span class="term" tabindex="0" data-tip="${esc(GLOSS[key][1])}">${text ?? esc(GLOSS[key][0])}</span>`;
// Static markup marks terms with data-term: text becomes a dotted term, an empty span an (i).
document.querySelectorAll('[data-term]').forEach(el => {
    const g = GLOSS[el.dataset.term];
    if (!g) return;
    if (el.textContent.trim()) {
        el.classList.add('term');
        el.tabIndex = 0;
        el.dataset.tip = g[1];
    } else {
        el.outerHTML = tip(`${g[0]}: ${g[1]}`);
    }
});

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
for (const type of ['mouseover', 'focusin']) {
    document.addEventListener(type, e => {
        const t = e.target.closest?.('[data-tip]');
        t ? showTip(t) : hideTip();
    });
}
document.addEventListener('focusout', hideTip);
document.addEventListener('keydown', e => { if (e.key === 'Escape') hideTip(); });
window.addEventListener('scroll', hideTip, {passive: true});

// --- shared state: overview (/api/overview) and the frozen rules (/api/frozen) --------
// Refetched with every section load, so the header, the trust strip and the section always agree.
let OVERVIEW = null, FROZEN = null;
async function refreshShared() {
    [OVERVIEW, FROZEN] = await Promise.all([getJson('/api/overview'), getJson('/api/frozen')]);
    renderTrustPills();
    $('footer-port').innerHTML = OVERVIEW.port_sha256
        ? `Python model version <code data-tip="sha256 of port/aermod_py: ${esc(OVERVIEW.port_sha256)}" tabindex="0">${esc(OVERVIEW.port_sha256.slice(0, 12))}</code>` : '';
}

// Plain-English explanations of the metrics, with the thresholds read from compare.py.
function glossary() {
    const r = FROZEN.rules, tol = r.slope_tolerance, rel = Number(r.relative_tolerance).toExponential(0);
    return {
        relPct: `${+(r.relative_tolerance * 100).toPrecision(3)}%`,
        slopePct: `${+(tol * 100).toPrecision(3)}%`,
        pctl: `${r.percentile}%`,
        sigPct: `${+(r.significant_fraction * 100).toPrecision(3)}%`,
        slope: `Plot every hourly concentration from the port against the reference and fit a line. A perfect port lies on a slope of exactly 1. The EPA rule allows 1 ± ${tol} (${+(tol * 100).toFixed(3)}%) and checks all three definitions EPA's kit uses: through the origin, ordinary least squares, and the ratio of the means.`,
        zero: `Share of paired hourly values where the port and the reference agree on whether there is any concentration at all (whether the plume reached the receptor). Must be at least ${pct(r.zero_agreement_min)}.`,
        p99: `Relative error |port − reference| / reference at the ${r.percentile}th percentile, over every value at least ${+(r.significant_fraction * 100).toFixed(2)}% of the case maximum. Must be ≤ ${rel}. 0 means the numbers are identical.`,
        h4h: `H4H is the "high fourth-high": at each receptor, the 4th-highest daily maximum 1-hour concentration in a year (the highest, for records under about 100 days). It is the design value regulators compare with the 1-hour standard. Every receptor must match within ${rel} relative; the count shows receptors that do not.`,
        epa: `The EPA rule: best-fit slope within 1 ± ${tol}, against EPA's own shipped output when the case has one, otherwise against our gfortran build.`,
        strict: `The strict rule: always against our gfortran build of the same Fortran. Every row present, zero/nonzero agreement ≥ ${pct(r.zero_agreement_min)}, p99 relative error ≤ ${rel}, and every receptor's H4H within ${rel}.`,
        holdout: GLOSS.holdout[1],
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
// Cases that count towards the public "matches EPA" claim: Tier B only once it passes.
function caseTotals(o) {
    const tiers = o.tiers.B.status === 'passing' ? ['A', 'B'] : ['A'];
    return tiers.map(t => tierCount(o.tiers[t])).reduce((a, c) => ({passing: a.passing + c.passing, total: a.total + c.total}), {passing: 0, total: 0});
}
const allMatch = o => {
    const c = caseTotals(o);
    return c.total > 0 && c.passing === c.total && o.tiers.A.status === 'passing';
};
const certifiedScope = o => o.certified_tiers.length ? `Tier ${o.certified_tiers.join(' + ')}` : '';
const certDate = () => STATIC?.ci ? longDate(STATIC.ci.completed_at) : '';

function renderTrustPills() {
    const o = OVERVIEW, c = caseTotals(o), p = o.provenance;
    const pill = (cls, text, why) => `<li class="pill ${cls}" tabindex="0" data-tip="${esc(why)}">${ic(cls)}<span>${text}</span></li>`;
    const pills = [];
    pills.push(o.tiers.A.status === 'not_scored'
        ? pill('neutral', 'Not yet compared with EPA here', 'Run make ref refs suite-tier-a to score the model on this machine.')
        : pill(allMatch(o) ? 'ok' : 'bad', `Matches EPA on <b>${c.passing}/${c.total}</b> test cases`,
            `Every one of EPA's official AERMOD test cases in scope is run through both EPA's model and this one and compared hour by hour. Scores from ${o.scores.source ?? 'no scores yet'}.`));
    if (STATIC) {
        pills.push(pill(o.certified ? 'ok' : 'bad', o.certified ? `Certified by automatic check · ${esc(certDate())}` : 'Not certified',
            `${STATIC.label}. ${GLOSS.ci[1]}`));
    } else {
        pills.push(pill(o.certified ? 'ok' : 'neutral', o.certified ? 'Certified on this computer' : 'Not yet certified here',
            o.certified ? 'Every certification criterion holds now: see Proof it\'s accurate.'
                : 'Certification needs the model scored on this machine: run make ref refs suite-tier-a, then reload.'));
    }
    pills.push(pill(p.python_files && p.ok ? 'ok' : p.python_files ? 'bad' : 'neutral',
        !p.python_files ? 'No model yet' : p.ok ? 'Zero hand edits to the model' : 'Model files not traced',
        `${p.python_files} Python files, each traced to the saved AI reply that wrote it (${p.interactions} AI requests).`));
    $('trust-pills').innerHTML = pills.join('');
}

// --- How it was built ------------------------------------------------------------------
async function loadPort() {
    await refreshShared();
    const [runs, snapshots, tokens, prov] = await Promise.all([getJson('/api/runs'), getJson('/api/results'), getJson('/api/tokens'), getJson('/api/provenance')]);
    const G = glossary(), o = OVERVIEW.argon;
    const pyFiles = prov.files.filter(f => f.file.endsWith('.py')), traced = pyFiles.filter(f => !f.problem).length;
    const all = runs.flatMap(r => r.interactions);
    const tier = OVERVIEW.tiers.B.status === 'passing' && tokens.B ? 'B' : 'A', tok = tokens[tier];
    const kpi = (v, k, d, t) => `<div class="kpi"><div class="v">${v}</div><div class="k">${k}${t ? ' ' + tip(t) : ''}</div><div class="d">${d}</div></div>`;
    $('built-kpis').innerHTML = [
        kpi(tok ? fmt(tok.lines) : '–', 'lines of EPA Fortran translated', tok ? `${fmt(tok.units)} routines of AERMOD's core physics` : 'run python pack.py',
            'The in-scope part of AERMOD: the dispersion physics for stacks, with and without building wake. Reading inputs and writing reports is handled by separate, human-written and separately checked code.'),
        kpi(fmt(o.interactions), 'AI requests in total', `across ${runs.length} recorded runs`, ''),
        kpi(o.cost_usd === null ? '–' : usd(o.cost_usd), 'total AI cost', o.cost_complete ? 'every request priced' : 'partial: some requests unpriced', ''),
        kpi(pyFiles.length ? `${prov.ok ? '' : ic('bad')}${traced}/${pyFiles.length}` : '–', 'model files traced to the AI',
            prov.ok ? 'zero hand edits' : `trace check failed: ${prov.problems.length} problem${prov.problems.length === 1 ? '' : 's'}, hand edits not ruled out`, G.provenance),
    ].join('');

    const by = kind => runs.filter(r => r.kind === kind && r.replies > 0);
    const cost = rs => rs.reduce((a, r) => a + (r.cost_usd ?? 0), 0);
    const port = by('port'), repair = by('repair'), edits = by('edit');
    const portFiles = new Set(port.flatMap(r => r.interactions.flatMap(i => i.files))).size;
    const kept = repair.reduce((a, r) => a + (r.patches_kept ?? 0), 0);
    const c = caseTotals(OVERVIEW);
    const steps = [
        ['Translate', port.length ? `${port.length === 1 ? 'One request' : `${port.length} requests`}: the AI read the core of AERMOD and wrote the Python package (${portFiles} files, ${usd(cost(port))}).` : 'Not run yet.'],
        ['Repair automatically', repair.length ? `An automatic loop compared the result with EPA's and sent the AI what differed. ${kept} fix${kept === 1 ? ' was' : 'es were'} kept, each only because no test got worse (${usd(cost(repair))}).` : 'No repairs recorded.'],
        ['Extend', edits.length ? `${edits.length} smaller follow-up requests added building-wake physics (PRIME) and fixed small issues (${usd(cost(edits))}).` : 'No follow-up requests recorded.'],
        ['Verify', `${c.passing} of ${c.total} EPA test cases match, rechecked automatically on every change. The scoring rules are locked.`],
    ];
    $('timeline').innerHTML = steps.map(([t, d], i) => `<li><span class="num">${i + 1}</span><div><b>${t}</b><p>${esc(d)}</p></div></li>`).join('');

    $('spend').innerHTML = [
        ['', 'Argon interactions', fmt(o.interactions), `across ${runs.length} run${runs.length === 1 ? '' : 's'} in agent/runs/`],
        [G.billed, 'Billed input tokens', fmt(o.usage.total_input_tokens), 'what Argon charged as input'],
        ['', 'Output + thinking tokens', fmt(o.usage.total_output_tokens + o.usage.total_thought_tokens),
         `${fmt(o.usage.total_output_tokens)} output, ${fmt(o.usage.total_thought_tokens)} thinking`],
        ['Sum of the per-interaction costs in results/tier_*.md.', 'Total spend',
         o.cost_usd === null ? 'not recorded' : `${usd(o.cost_usd)}${o.cost_complete ? '' : ' (partial)'}`,
         o.prices.length ? `priced in ${o.prices.map(x => x.path).join(', ')}` : 'no price table yet'],
    ].map(([t, k, v, d]) => `<div class="kpi"><div class="v">${v}</div><div class="k">${esc(k)}${t ? ' ' + tip(t) : ''}</div><div class="d">${esc(d)}</div></div>`).join('');

    const calls = Object.fromEntries(snapshots.flatMap(s => s.calls).map(x => [x.interaction_id, x]));
    const tiers = ['A', 'B'].filter(t => tokens[t]);
    $('token-method').textContent = tiers.length ? `(${tokens[tiers[0]].method})` : '';
    $('token-table').innerHTML = tiers.length === 0
        ? empty('<b>context/tokens.json is missing.</b> Run <code>python pack.py</code>.')
        : table(['Tier', {label: 'Units', cls: 'num', tip: 'Fortran program units (subroutines, functions, modules) packed into the prompt.'},
                 {label: 'Lines', cls: 'num'},
                 {label: 'Tokens', cls: 'num', tip: 'Comment-stripped Fortran. agent/port.py sends this by default.'},
                 {label: 'With comments', cls: 'num'}],
            tiers.map(t => `<tr><td><b>Tier ${t}</b><br><span class="muted xsmall">${t === 'A' ? 'no building wake' : 'adds PRIME building wake'}</span></td>
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
                    ? `<br><span class="badge neutral" data-tip="${esc(G.billed)}">${(r.usage.total_input_tokens / r.prompt_tokens).toFixed(1)}× prompt</span>` : ''}</td>
                <td class="num">${fmt(r.usage.total_output_tokens + r.usage.total_thought_tokens)}</td>
                <td class="num">${usd(r.cost_usd)}</td>
                <td>${outcome(r)}</td>
            </tr>`));
    document.querySelectorAll('tr[data-run]').forEach(tr => {
        tr.onclick = () => showRun(tr.dataset.run);
        tr.onkeydown = e => { if (e.key === 'Enter') showRun(tr.dataset.run); };
    });
    // Drawn after the fold opens: a closed <details> has no width to size the chart to.
    const drawTokens = () => {
        $('token-chart').innerHTML = all.length === 0
            ? empty('<b>No Argon interactions recorded yet.</b> Run <code>python agent/port.py --tier A</code>, then reload.')
            : tokenChart(runs, calls, widthOf('token-chart', 420, 900));
    };
    onOpen($('token-chart'), drawTokens);

    const commits = await getJson('/api/commits?limit=20');
    $('commits').innerHTML = commits.length === 0
        ? empty('No git history for <code>port/aermod_py</code> in this checkout.')
        : `<ul class="commits">${commits.map(x => `<li><code>${esc(x.hash)}</code><span class="muted">${esc(x.date.slice(0, 10))}</span><span>${esc(x.subject)}</span></li>`).join('')}</ul>`;
}

// Runs fn now if el's enclosing <details> is open, and again whenever it opens.
function onOpen(el, fn) {
    const d = el.closest('details');
    if (!d) return fn();
    if (d.open) fn();
    d.ontoggle = () => { if (d.open) fn(); };
}

const TOKEN_SERIES = [
    ['prompt', 'Prompt sent', '#3d6f99'],
    ['billed', 'Billed input', '#a7bdd1'],
    ['output', 'Output', '#3a4047'],
    ['thinking', 'Thinking', '#b9bfc6'],
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
    const left = 104, right = 70, barH = 14, gap = 4, groupGap = 18, titleH = 18, top = 6, axisH = 40;
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
                s += `<text class="faint" x="${left + 4}" y="${y + barH - 3}" font-size="11">not recorded</text>`;
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
    $('run-detail').innerHTML = `<div class="run-detail"><h3 class="sub-h"><code>${esc(id)}</code></h3>` +
        (run.token_method ? `<p class="muted small">Prompt tokens: ${fmt(run.prompt_tokens)} by ${esc(run.token_method)}</p>` : '') +
        table(['Argon interaction', 'Step', 'Files written', {label: 'Billed input', cls: 'num'}, {label: 'Output', cls: 'num'},
               {label: 'Thinking', cls: 'num'}, {label: 'Seconds', cls: 'num'}, {label: 'Cost', cls: 'num'}, 'Repair decision'],
            run.interactions.map(i => `<tr><td class="mono">${esc(i.id)}<br><span class="muted">${esc(i.status)}, ${esc(i.path)}</span></td>
                <td>${esc(i.step ?? '–')}${i.iteration ? ` ${i.iteration}` : ''}</td>
                <td class="mono">${i.files.map(esc).join(', ') || '–'}</td>
                <td class="num">${fmt(i.usage.total_input_tokens)}</td><td class="num">${fmt(i.usage.total_output_tokens)}</td>
                <td class="num">${fmt(i.usage.total_thought_tokens)}</td><td class="num">${i.seconds ? fmt(Math.round(i.seconds)) : '–'}</td>
                <td class="num">${usd(i.cost_usd)}</td>
                <td>${i.decision ? `${badge(i.decision.accepted ? 'ok' : 'bad', i.decision.accepted ? 'kept' : 'rolled back')} ${esc(i.decision.reason ?? '')}
                    <div class="muted small">${esc(i.decision.hypothesis ?? '')}</div>` : '–'}</td></tr>`)) + '</div>';
}

// --- Proof it's accurate -------------------------------------------------------------
const TIER_SCOPE = {A: 'stacks in open terrain, no building wake', B: 'adds PRIME building wake (downwash)'};
const CASE_PLAIN = {A: 'Stack in open terrain', B: 'Stack beside buildings'};
const REF_PLAIN = ref => /EPA/.test(ref) ? 'vs EPA\'s published results' : 'vs EPA\'s Fortran program, compiled by us';
const receptorsOf = r => Number(String(r?.h4h_fails ?? '').split('/')[1]) || 0;
const receptorFails = r => Number(String(r?.h4h_fails ?? '').split('/')[0]) || 0;

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
        body = `<dl class="metrics">
            <dt>EPA rule ${tip(G.epa)}</dt><dd>${verdict(r.epa_pass)}</dd>
            <dt>Best-fit slope ${tip(G.slope)}</dt><dd tabindex="0" data-tip="${esc(slopes)}">${fixed(r.slope, 6)}</dd>
            <dt>Strict rule ${tip(G.strict)}</dt><dd>${verdict(r.strict_pass)}</dd>
            <dt>Zero/nonzero agreement ${tip(G.zero)}</dt><dd>${isNum(r.zero_agreement) ? `${(100 * r.zero_agreement).toFixed(3)}%` : '–'}</dd>
            <dt>p99 relative error ${tip(G.p99)}</dt><dd>${p99}</dd>
            <dt>Largest absolute difference</dt><dd>${isNum(r.max_abs_diff) ? (Number(r.max_abs_diff) === 0 ? '0 (identical)' : `${Number(r.max_abs_diff).toExponential(2)} µg/m³`) : 'not recorded'}</dd>
            <dt>H4H receptors failing ${tip(G.h4h)}</dt><dd>${esc((r.h4h_fails ?? '–').replace('/', ' / '))}</dd>
        </dl>`;
    } else {
        body = `<pre>${esc(r.summary ?? '')}</pre>`;
    }
    return `<div class="case ${cls}"><div class="case-head"><code>${esc(name)}</code>${badge(bcls, label)}</div>
        <div class="meta">${meta}</div>${body}</div>`;
}

function slopeChart(rows, tol, W) {
    const left = 150, right = 24, rowH = 24, top = 30, axisH = 44;
    const H = top + rows.length * rowH + axisH;
    const lo = 1 - 4 * tol, hi = 1 + 4 * tol;
    const x = v => left + (W - left - right) * (Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo);
    const kinds = [['slope', 'through origin', 'circle', '#3d6f99'], ['slope_ols', 'OLS (EPA R script)', 'square', '#1d2125'], ['mean_ratio', 'ratio of means', 'diamond', '#8aa6c0']];
    const plotBottom = top + rows.length * rowH;
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Best-fit slope by case">`;
    s += `<rect x="${x(1 - tol)}" y="${top - 6}" width="${x(1 + tol) - x(1 - tol)}" height="${plotBottom - top + 6}" class="band-ok" data-tip="Pass band: 1 ± ${tol}"/>`;
    s += `<text class="ok-text" x="${x(1)}" y="${top - 12}" text-anchor="middle" font-size="11">pass band 1 ± ${tol}</text>`;
    for (let k = -4; k <= 4; k++) {
        const v = 1 + k * tol;
        s += `<line class="grid" x1="${x(v)}" x2="${x(v)}" y1="${top - 6}" y2="${plotBottom}"/>`;
        s += `<text x="${x(v)}" y="${plotBottom + 15}" text-anchor="middle" font-size="11">${v.toFixed(3)}</text>`;
    }
    s += `<line class="ok-line" x1="${x(1)}" x2="${x(1)}" y1="${top - 6}" y2="${plotBottom}"/>`;
    s += `<line class="tick" x1="${left}" x2="${W - right}" y1="${plotBottom}" y2="${plotBottom}"/>`;
    s += `<text class="axis-title" x="${left + (W - left - right) / 2}" y="${H - 6}" text-anchor="middle">best-fit slope of port vs reference (unitless; 1 = identical; values outside the axis are pinned to its edge)</text>`;
    rows.forEach((r, i) => {
        const yc = top + i * rowH + rowH / 2;
        if (i % 2 === 0) s += `<rect class="stripe" x="${left}" y="${yc - rowH / 2}" width="${W - left - right}" height="${rowH}"/>`;
        s += `<text class="mono${r.muted ? ' faint' : ''}" x="${left - 10}" y="${yc + 4}" text-anchor="end" font-size="12">${esc(r.name)}</text>`;
        kinds.forEach(([key, label, shape, color], k) => {
            const v = r[key];
            if (!isNum(v)) return;
            const cx = x(v), cy = yc + (k - 1) * 5, off = v < lo || v > hi;
            const fill = r.muted ? '#a3acb6' : color;
            const t = `data-tip="${esc(`${r.name}: ${label} slope ${Number(v).toFixed(6)}${off ? ' (off the axis)' : ''}`)}"`;
            if (shape === 'circle') s += `<circle cx="${cx}" cy="${cy}" r="4.5" fill="${fill}" ${t}/>`;
            else if (shape === 'square') s += `<rect x="${cx - 4}" y="${cy - 4}" width="8" height="8" fill="${fill}" ${t}/>`;
            else s += `<path d="M${cx} ${cy - 5.5}L${cx + 5.5} ${cy}L${cx} ${cy + 5.5}L${cx - 5.5} ${cy}Z" fill="${fill}" ${t}/>`;
            if (off && k === 0) s += `<text class="bad-text" x="${v < lo ? cx + 9 : cx - 9}" y="${yc + 4}" text-anchor="${v < lo ? 'start' : 'end'}" font-size="11">${v < lo ? '◀' : '▶'} ${Number(v).toFixed(3)}</text>`;
        });
    });
    const legend = kinds.map(([, label, , c]) => `<span><i style="background:${c};border-radius:50%"></i>${label}</span>`).join('')
        + (rows.some(r => r.muted) ? '<span><i style="background:#a3acb6"></i>Tier B, in progress</span>' : '');
    return `<div class="legend">${legend}</div>${s}</svg>`;
}

const CRITERIA = {
    suite_found: ['Scores are fresh for this checkout', 'The port was scored on this machine (make suite-tier-a or make suite-port wrote out/suite_port.json), not only read from a committed snapshot.'],
    compare_approved: ['The scoring script is the approved one', 'harness/compare.py matches the sha256 pinned in harness/compare.sha256.'],
    compare_frozen: ['The scores came from that script', 'The suite recorded which compare.py produced it, and it is the current one.'],
    scored_this_port: ['The scores belong to this exact model version', 'The Tier A cases were scored with the same package digest port/aermod_py has now.'],
    tier_a_epa: ['Tier A passes the EPA rule', 'Every Tier A training case: all three best-fit slopes within tolerance.'],
    tier_a_strict: ['Tier A passes the strict rule', 'Every Tier A training case matches our reference build row by row, including each receptor\'s H4H design value.'],
    port_exists: ['A model exists', 'port/aermod_py contains generated Python files.'],
    provenance: ['Every file came from the AI', 'Each file traces to a saved, completed Argon interaction; any hand edit breaks the trace.'],
};
// The static export scores from the CI snapshot instead of this machine's out/suite_port.json.
const STATIC_CRITERIA = {
    suite_found: ['Scores come from CI', 'The port-suite job of the latest green main CI run scored the port with the frozen compare.py; its out/suite_port.json is committed as results/ci_port_suite.json.'],
};

async function loadProof() {
    await refreshShared();
    const G = glossary(), r = FROZEN.rules, tol = r.slope_tolerance, rel = Number(r.relative_tolerance).toExponential(0);
    const [data, cert, prov] = await Promise.all([getJson('/api/test-results'), getJson('/api/certify'), getJson('/api/provenance')]);
    const tiers = OVERVIEW.tiers, c = caseTotals(OVERVIEW);
    const claimTiers = tiers.B.status === 'passing' ? ['A', 'B'] : ['A'];
    const names = claimTiers.flatMap(t => [...tiers[t].training.cases, ...tiers[t].holdout.cases]);
    const holdouts = names.filter(n => data.cases[n]?.tier === 'holdout');

    $('proof-title').textContent = allMatch(OVERVIEW)
        ? `Matches EPA's official AERMOD on all ${c.total} EPA test cases`
        : `Matches EPA's official AERMOD on ${c.passing} of ${c.total} EPA test cases`;

    // Certification: computed by /api/certify (the static export ran it on the CI snapshot).
    const certified = cert.certified, failing = cert.criteria.filter(x => !x.ok);
    const criteria = STATIC ? {...CRITERIA, ...STATIC_CRITERIA} : CRITERIA;
    const needsScoring = failing.length > 0 && failing.every(x => ['suite_found', 'scored_this_port'].includes(x.name));
    const scope = OVERVIEW.certified_tiers.includes('B') ? 'industrial stacks on flat, rural terrain, with and without building wake'
        : 'industrial stacks on flat, rural terrain, without building wake';
    const cls = certified ? 'ok' : !STATIC && needsScoring ? 'neutral' : 'bad';
    const title = certified ? 'Certified: this exact model version matches EPA'
        : !STATIC && needsScoring ? 'Not yet verified on this computer' : 'Not certified';
    const what = certified
        ? `An automatic check reran EPA's test cases on this exact version of the model, scored them with the locked rules, and every one of the ${cert.criteria.length} requirements passed. Covers ${scope}.`
        : !STATIC && needsScoring
            ? 'Certification needs the model scored on this machine. Run <code>make ref refs suite-tier-a</code>, then reload.'
            : `${failing.length} of ${cert.criteria.length} requirements fail: ${failing.map(x => esc((criteria[x.name] ?? [x.name])[0].toLowerCase())).join('; ')}.`;
    const evidence = STATIC
        ? `<p class="cert-label">${ic(certified ? 'ok' : 'bad')}<b>${esc(STATIC.label)}</b>${STATIC.ci
            ? ` · ${extLink(STATIC.ci.run_url, 'View the check')} · ${extLink(ciCommitUrl(), 'View the code')}` : ''}</p>`
        : `<p class="cert-label muted">Recomputed on every page load from the scores, the scoring script, the model files and their trace.</p>`;
    $('cert-card').className = `card cert ${cls}`;
    $('cert-card').innerHTML = `<div class="cert-seal" aria-hidden="true">${ICON[cls]}</div><div>
        <p class="eyebrow">Certification ${tip(GLOSS.ci[1])}</p>
        <h3>${esc(title)}</h3><p>${what}</p>${evidence}</div>`;

    const receptors = names.reduce((a, n) => a + receptorsOf(data.results[n]), 0);
    const recFails = names.reduce((a, n) => a + receptorFails(data.results[n]), 0);
    const holdPass = holdouts.filter(n => data.results[n]?.passes).length;
    const kpi = (cls2, v, k, d, t) => `<div class="kpi ${cls2}"><div class="v">${ic(cls2)}${v}</div><div class="k">${k}${t ? ' ' + tip(t) : ''}</div><div class="d">${d}</div></div>`;
    $('proof-kpis').innerHTML = [
        kpi(allMatch(OVERVIEW) ? 'ok' : 'bad', `${c.passing}/${c.total}`, 'EPA test cases match', 'hour by hour, at every location'),
        kpi(holdouts.length && holdPass === holdouts.length ? 'ok' : 'bad', `${holdPass}/${holdouts.length}`, 'held-back cases match', 'never used while building the model', G.holdout),
        kpi(receptors && recFails === 0 ? 'ok' : 'bad', receptors ? `${fmt(receptors - recFails)}/${fmt(receptors)}` : '–', 'locations where the regulator\'s number matches',
            'the design value compared with the limit', GLOSS.worst[1]),
        kpi(OVERVIEW.compare_frozen ? 'ok' : 'bad', OVERVIEW.compare_frozen ? 'Locked' : 'Changed', 'scoring rules', 'fingerprint unchanged since approval', G.frozen),
    ].join('');

    $('check-steps').innerHTML = [
        ['Run both models', 'Each EPA test case goes through EPA\'s original Fortran AERMOD and through the Python version, with identical inputs and weather.'],
        ['Compare every number', `Every hourly result at every location is compared. ${G.pctl} of significant concentrations (at least ${G.sigPct} of the case maximum) must agree within ${G.relPct}, and the number regulators compare with the limit must match at every location.`],
        ['Lock the rules', 'The scoring script is locked with a digital fingerprint, so the pass mark cannot be loosened after seeing results. An independent server reruns everything on every change.'],
    ].map(([t, d], i) => `<li><span class="num">${i + 1}</span><div><b>${t}</b><p>${esc(d)}</p></div></li>`).join('');

    $('cases-sub').innerHTML = !data.source ? 'Not scored yet.'
        : STATIC && data.source === 'results/ci_port_suite.json'
            ? `Scored by ${ciRun()} on ${esc(longDate(STATIC.ci.completed_at))}.`
            : `Scored ${esc(data.suite_time ?? '')} (<code>${esc(data.source)}</code>).`;
    $('case-list').innerHTML = names.map(n => {
        const res = data.results[n], info = data.cases[n] ?? {};
        const [, bcls, label] = caseState(res, tiers[info.tests_tier]?.status);
        const rc = receptorsOf(res);
        return `<div class="case-tile ${bcls}">
            <div class="ct-top">${badge(bcls, label === 'pass' ? 'Matches EPA' : label)}${info.tier === 'holdout' ? `<span class="tag tag-steel" tabindex="0" data-tip="${esc(G.holdout)}">Held back</span>` : ''}</div>
            <div class="ct-name">${esc(CASE_PLAIN[info.tests_tier] ?? 'EPA test case')}</div>
            <div class="ct-meta">${rc ? `${fmt(rc)} locations · ` : ''}${esc(REF_PLAIN(info.reference ?? ''))}</div>
            <code class="ct-code">${esc(n)}</code></div>`;
    }).join('');

    // For engineers.
    const src = $('score-source');
    if (!data.source) {
        src.innerHTML = 'No scores yet: run <code>make suite-tier-a</code>.';
    } else if (data.suite_found) {
        src.innerHTML = `From ${STATIC ? `${ciRun()}, ` : ''}<code>${esc(data.source)}</code> (${esc(data.suite_time)}). ` +
            (data.hash_matches ? 'Scored with the current compare.py. ' : '<b>Scored with a different compare.py.</b> ') +
            (data.port_matches ? 'Scored the current port.' : '<b>The port changed since it was scored.</b>');
    } else if (data.source.startsWith('results/')) {
        src.innerHTML = `From the committed snapshot <code>${esc(data.source)}</code> (scored ${esc(data.suite_time ?? '?')}), ` +
            (data.hash_matches ? 'with the current compare.py. ' : '<b>with a different compare.py.</b> ') +
            'Run <code>make suite-tier-a</code> to rescore on this machine.';
    } else {
        src.innerHTML = `From <code>${esc(data.source)}</code>, the repair loop's last scoring. Run <code>make suite-tier-a</code> for scores tied to the port version.`;
    }
    $('case-groups').innerHTML = ['A', 'B'].map(t => {
        const ns = [...tiers[t].training.cases, ...tiers[t].holdout.cases];
        const st = tiers[t].status, tc = tierCount(tiers[t]);
        const pill = st === 'passing' ? badge('ok', `${tc.passing}/${tc.total} pass`) : st === 'failing' ? badge('bad', `${tc.passing}/${tc.total} pass`)
            : st === 'in_progress' ? badge('prog', 'in progress') : badge('neutral', 'not scored');
        const note = st === 'in_progress' && !tc.scored
            ? empty('<b>Tier B is being ported now.</b> Its cases appear here once <code>results/tier_B.md</code> or <code>out/suite_port.json</code> has Tier B passes.') : '';
        return `<div class="tier-head"><h3>Tier ${t}</h3><span class="muted">${TIER_SCOPE[t]}</span>${pill}</div>${note}
            <div class="cases">${ns.map(n => caseCard(n, data.results[n], data.cases[n], st, G)).join('')}</div>`;
    }).join('');
    const rows = ['A', 'B'].flatMap(t => [...tiers[t].training.cases, ...tiers[t].holdout.cases]
        .filter(n => isNum(data.results[n]?.slope))
        .map(n => ({name: n, ...data.results[n], muted: t === 'B' && tiers.B.status !== 'passing'})));
    onOpen($('slope-chart'), () => {
        $('slope-chart').innerHTML = rows.length ? slopeChart(rows, tol, widthOf('slope-chart', 560, 1200))
            : empty('<b>No slopes recorded yet.</b> The committed snapshot or <code>out/suite_port.json</code> supplies them.');
    });

    $('rules').innerHTML = `
        <div class="rule"><h3>EPA rule ${tip(G.epa)}</h3>
            <p class="against">Against EPA's own published output where the case has one, otherwise our build of the Fortran.</p>
            <ul><li>Across every hour and receptor, the Python model's concentrations agree with EPA's within ±${G.slopePct} overall.</li>
                <li class="mono-li">best-fit slope of port vs reference = 1 ± ${tol}; through origin, OLS and ratio of means must all pass</li></ul></div>
        <div class="rule"><h3>Strict rule ${tip(G.strict)}</h3>
            <p class="against">Always against our build of the same Fortran, hour by hour, receptor by receptor.</p>
            <ul><li>Every hourly result exists in both models (no missing x, y, date, averaging or group rows).</li>
                <li>Both agree on where the plume reaches, in at least ${pct(r.zero_agreement_min)} of hours.</li>
                <li>${G.pctl} of significant concentrations (at least ${G.sigPct} of the case maximum) match within ${G.relPct} (p${r.percentile} of |port − ref| / ref ≤ ${rel}).</li>
                <li>The regulatory design value (H4H, high fourth-high) matches at every receptor, within ${rel} relative.</li></ul></div>`;

    $('criteria').innerHTML = cert.criteria.map(x => {
        const [t, why] = criteria[x.name] ?? [x.name, ''];
        return `<li><span role="img" aria-label="${x.ok ? 'pass' : 'fail'}">${ic(x.ok ? 'ok' : 'bad')}</span>
            <div><div class="title">${esc(t)}</div><div class="why">${esc(why)}</div></div>
            <div class="detail"><span class="muted">${esc(x.name)}:</span> ${esc(x.detail)}</div></li>`;
    }).join('');
    const withB = cert.certified && OVERVIEW.certified_tiers.includes('B'), b = tiers.B;
    $('scope-note').innerHTML = `<p><b>What certification covers.</b> ${cert.certified ? `Certified scope: ${esc(certifiedScope(OVERVIEW))}. ` : ''}
        Tier A: point sources (stacks) on flat, rural terrain, 1-hour averages, no building downwash. Holdout cases are reported but are not
        certification criteria, so the repair loop can never be tuned to them. Tier B (PRIME building downwash): ${withB
            ? 'every Tier B case, training and holdout, passes in the same scoring of this exact model, so the certification extends to Tier B.'
            : b.status === 'passing'
                ? 'all its cases pass, but not in a scoring of this exact model on this machine; run <code>make suite-port</code> to extend certification to Tier B.'
                : 'in progress. Nothing here claims a Tier B result.'}
        Not ported by design: input parsing and output writing. The human-written <code>harness/glue.py</code> builds every setup value the
        physics reads and is checked bit for bit against an instrumented AERMOD build.</p>
        ${STATIC ? '<p>In this read-only demo, certification was computed when the site was exported (<code>tools/export_static.py</code>), from the scores the latest green main CI run recorded. It shows as certified only if that run scored exactly the committed Python model. Run <code>make demo</code> locally to recompute it.</p>' : ''}`;

    $('frozen').innerHTML = `
        <div class="hash"><div class="k">harness/compare.py now</div><div class="mono">${esc(FROZEN.compare_hash)}</div></div>
        <div class="hash"><div class="k">approved (harness/compare.sha256)</div><div class="mono">${esc(FROZEN.approved_hash ?? 'missing')}</div></div>
        <div class="hash center">${FROZEN.matches ? badge('ok', 'unchanged') : badge('bad', 'CHANGED')}</div>`;

    $('prov-status').innerHTML = prov.files.length === 0
        ? empty('<b>No port yet.</b> <code>port/aermod_py</code> holds only its README.')
        : `${badge(prov.ok ? 'ok' : 'bad', prov.ok ? 'verified' : 'unverified')} ${tip(G.provenance)} <b>${prov.files.length}</b> files from
           <b>${prov.interactions.length}</b> Argon interaction(s), checked by the same code as <code>split.py --verify</code>.`;
    $('prov-table').innerHTML = prov.files.length === 0 ? '' :
        table(['File', 'Argon interaction', 'Saved reply', 'Step', 'Status'], prov.files.map(f => `<tr>
            <td class="mono">aermod_py/${esc(f.file)}</td><td class="mono">${esc(f.interaction_id ?? '–')}</td>
            <td class="mono">${esc(f.reply ?? '–')}</td><td>${esc(f.step ?? '–')}</td>
            <td>${f.problem ? `${badge('bad', 'untraced')} ${esc(f.problem)}` : badge('ok', 'traced')}</td></tr>`));
}

// --- About ---------------------------------------------------------------------------
async function loadAbout() {
    await refreshShared();
    const cfg = WI ?? await getJson('/api/whatif/config');
    const yes = text => `<li>${ic('ok')}<span>${text}</span></li>`;
    const ex = text => `<li>${ic('neutral')}<span>${text}</span></li>`;
    $('about-scope').innerHTML = [
        yes(`<b>Real:</b> EPA's ${term('aermod', 'AERMOD')} physics, verified against EPA's test cases; a full year of real hourly weather (${esc(cfg.met.label.replace(/\s*\(.*\)$/, ''))}); the federal limits from 40 CFR part 50.`),
        ex('<b>Example data:</b> the plant, its stack, the emission change for each fuel mix and the background levels are illustrative, not data from a real plant.'),
        ex(`<b>One stack on flat, open ground.</b> Real studies add nearby buildings (${term('downwash', 'building wake')}), terrain, several stacks and a denser grid of points.`),
        ex('<b>One year of weather.</b> Permit studies use several years of local weather and monitored background.'),
        ex(`<b>${term('nox', 'NOx')} is counted entirely as NO₂</b>, which errs on the safe side.`),
        ex('<b>Not a permit application.</b> A fast screening answer that shows which changes are worth a full study.'),
    ].join('');
    $('glossary').innerHTML = Object.values(GLOSS).map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('');
}

// --- Fuel & Permit Check (what-if) -------------------------------------------------------
const WI_SLIDERS = {height: 'stack_height_m', diameter: 'stack_diameter_m',
                    temperature: 'exit_temperature_k', velocity: 'exit_velocity_ms'};
const WI_FMT = {height: v => `${v} m`, diameter: v => `${v} m`,
                temperature: v => `${Math.round(v - 273.15)} °C <small>(${v} K)</small>`, velocity: v => `${v} m/s`};
const LB_PER_HR_PER_G_S = 3600 / 453.59237;
const gs = v => `${fixed(v, 1)} g/s <small>(${fmt(Math.round(v * LB_PER_HR_PER_G_S))} lb/hr)</small>`;
const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
const COMPASS_WORDS = ['north', 'north-northeast', 'northeast', 'east-northeast', 'east', 'east-southeast', 'southeast', 'south-southeast',
    'south', 'south-southwest', 'southwest', 'west-southwest', 'west', 'west-northwest', 'northwest', 'north-northwest'];
const compassIdx = deg => Math.round((((deg % 360) + 360) % 360) / 22.5) % 16;
const compass = deg => COMPASS[compassIdx(deg)];
const km = m => (m = Math.round(m)) >= 1000 ? `${+(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`;
const ug = x => `${Number(x).toLocaleString('en-US', {maximumFractionDigits: x < 10 ? 2 : 1})} µg/m³`;
const ordinal = n => `${n}${n === 1 ? 'st' : n === 2 ? 'nd' : n === 3 ? 'rd' : 'th'}`;
const POL_SHORT = {SO2: 'SO₂', NOX: 'NOx'};
const POL_NAME = {SO2: 'Sulfur dioxide', NOX: 'Nitrogen oxides'};
const POL_TERM = {SO2: 'so2', NOX: 'nox'};
// The NOx standard is the NO2 NAAQS: all NOx is counted as NO2.
const LIMIT_POL = {SO2: 'SO₂', NOX: 'NO₂'};
const POL_NOTE = {NOX: ', counted as NO₂'};
const polShort = k => POL_SHORT[k] ?? k;
const LIMIT_NAME = {one_hour: '1-hour limit', annual: 'yearly-average limit'};
const levelOf = s => !s.passes ? 'bad' : s.percent_of_limit >= NEAR_LIMIT_PCT ? 'warn' : 'ok';
const LEVEL_TEXT = {ok: 'Within limit', warn: 'Close to limit', bad: 'Over limit', neutral: 'No answer here'};
const mixShort = k => (WI.fuel_mix[k]?.label ?? k).replace(/\s*\(.*\)$/, '');
let WI = null, wiTimer = null, wiLast = null;

const pollutant = () => document.querySelector('input[name="wi-pollutant"]:checked')?.value ?? WI.defaults.pollutant;
const fuel = () => document.querySelector('input[name="wi-fuel"]:checked')?.value ?? WI.defaults.fuel_mix;
const gridValue = id => WI.grid[WI_SLIDERS[id]][Number($(`wi-${id}`).value)];

async function loadWhatif() {
    const shared = refreshShared();
    if (!WI) {
        WI = await getJson('/api/whatif/config');
        initWhatif();
    }
    await Promise.all([shared, updateWhatif()]);
    renderTrust();
}

function renderFuelOptions() {
    const pol = pollutant(), today = WI.fuel_mix[WI.defaults.fuel_mix], chosen = fuel();
    $('wi-fuel').querySelectorAll('.opt').forEach(el => el.remove());
    $('wi-fuel').insertAdjacentHTML('beforeend', Object.entries(WI.fuel_mix).map(([k, m]) => {
        const change = Math.round(100 * (m.emission_factor[pol] / today.emission_factor[pol] - 1));
        const sub = k === WI.defaults.fuel_mix ? 'Today\'s operation'
            : `${polShort(pol)} emissions ${change > 0 ? '+' : change < 0 ? '−' : '±'}${Math.abs(change)}% vs today`;
        return `<label class="opt"><input type="radio" name="wi-fuel" value="${esc(k)}"${k === chosen ? ' checked' : ''}>
            <span><b>${esc(mixShort(k))}</b><small>${esc(sub)}</small></span></label>`;
    }).join(''));
}

function initWhatif() {
    const s = WI.defaults, n = WI.receptors.directions * WI.receptors.distances_m.length;
    const alt = Object.values(WI.fuel_mix).map(m => m.label.match(/\(([^)]*)\)/)?.[1]).find(Boolean);
    $('wi-plant').innerHTML = `Example plant: one ${s.stack_height_m} m kiln ${term('stack', 'stack')} on flat, open ground, checked at ${n} points
        up to ${Math.max(...WI.receptors.distances_m) / 1000} km away over a full year of hourly weather.
        ${alt ? `Alternative fuels here: ${esc(alt.replace('tyres', 'tires').replace('RDF', 'refuse-derived fuel (RDF)'))}.` : ''}`;
    $('wi-pollutant').insertAdjacentHTML('beforeend', Object.keys(WI.pollutants).map(k =>
        `<label class="opt"><input type="radio" name="wi-pollutant" value="${esc(k)}"${k === s.pollutant ? ' checked' : ''}>
            <span><b>${esc(POL_NAME[k] ?? WI.pollutants[k].label)} <span class="chem">${esc(polShort(k))}</span></b></span></label>`).join(''));
    renderFuelOptions();
    $('wi-sources').innerHTML = `
        <div class="source"><span class="lab">Real</span>Dispersion computed by the Python AERMOD verified on the Proof page;
            a full year of hourly weather from ${esc(WI.met.label)}; federal limits (NAAQS) from 40 CFR part 50.</div>
        <div class="source illus"><span class="tag">Illustrative</span>Fuel-mix effects, emission rates, stack defaults and background
            levels are example values, not plant data. They come from <code>${esc(WI.config_path ?? 'whatif/kiln.toml')}</code>.</div>`;
    for (const [id, key] of Object.entries(WI_SLIDERS)) {
        const el = $(`wi-${id}`);
        el.min = 0; el.max = WI.grid[key].length - 1; el.step = 1;
        el.value = Math.max(0, WI.grid[key].indexOf(WI.defaults[key]));
    }
    applyPollutant();
    if (STATIC) {
        $('wi-controls').querySelectorAll('input').forEach(el => { el.disabled = true; });
        $('wi-advanced-note').innerHTML = `<p class="demo-note">${ic('neutral')}<span><b>Fixed in this online demo.</b> It shows the preset fuel mixes only.
            Moving the stack, emissions or site needs the live model: we run it on your plant's data.
            <span class="muted">Engineers can run it locally with <code>make demo</code>.</span></span></p>`;
    }
    $('wi-pollutant').addEventListener('change', () => { applyPollutant(); renderFuelOptions(); scheduleWhatif(0); });
    $('wi-fuel').addEventListener('change', () => { applyPreset(); scheduleWhatif(0); });
    $('wi-bldg').onchange = () => { $('wi-bldg-box').hidden = !$('wi-bldg').checked; scheduleWhatif(); };
    $('wi-metric').onchange = () => wiLast && renderMaps(wiLast);
    for (const id of ['height', 'diameter', 'temperature', 'velocity', 'emission', 'bg1', 'bgA', 'bh', 'bw', 'bd', 'urban', 'terrain']) {
        $(`wi-${id}`).addEventListener('input', () => scheduleWhatif());
    }
}

function applyPreset() {
    const p = WI.presets[pollutant()][fuel()];
    $('wi-emission').value = p.emission_rate_gs;
    $('wi-temperature').value = WI.grid.exit_temperature_k.indexOf(p.exit_temperature_k);
}

function applyPollutant() {
    const pol = WI.pollutants[pollutant()];
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

function scheduleWhatif(delay = 120) {
    wiLabels();
    clearTimeout(wiTimer);
    wiTimer = setTimeout(() => updateWhatif().catch(err => console.error(err)), delay);
}

async function updateWhatif() {
    wiLabels();
    const bldg = $('wi-bldg').checked;
    const q = new URLSearchParams({
        pollutant: pollutant(), height: gridValue('height'), diameter: gridValue('diameter'),
        temperature: gridValue('temperature'), velocity: gridValue('velocity'), emission: $('wi-emission').value,
        background_1h: $('wi-bg1').value || 0, background_annual: $('wi-bgA').value || 0,
        building_height: bldg ? $('wi-bh').value : 0, building_width: bldg ? $('wi-bw').value : 0,
        building_distance: bldg ? $('wi-bd').value : 0,
        urban: $('wi-urban').checked, complex_terrain: $('wi-terrain').checked,
    });
    const data = await getJson(STATIC ? `/api/whatif/${pollutant()}/${fuel()}` : `/api/whatif?${q}`);
    wiLast = data;
    renderAnswer(data);
    renderMaps(data);
    renderStandards();
    renderArgonNote(data);
}

const worstOf = r => ['one_hour', 'annual'].reduce((a, k) => r[k].percent_of_limit > r[a].percent_of_limit ? k : a, 'one_hour');

function gauge(pol, key, s) {
    const level = levelOf(s), p = s.percent_of_limit;
    const max = Math.max(110, Math.ceil(p * 1.08 / 10) * 10);
    const at = v => `${(100 * Math.min(v, max) / max).toFixed(2)}%`;
    const bgPct = 100 * s.background_ugm3 / s.limit_ugm3;
    const name = `${LIMIT_NAME[key][0].toUpperCase()}${LIMIT_NAME[key].slice(1)}`;
    return `<div class="gauge ${level}">
        <div class="g-head"><span class="g-name">${esc(name)}</span>
            <span class="g-val">${ic(level)}<b>${Math.round(p)}%</b> <span class="muted">${LEVEL_TEXT[level].toLowerCase()}</span></span></div>
        <div class="g-bar" role="img" aria-label="${esc(`${name}: ${Math.round(p)}% of the limit, ${LEVEL_TEXT[level]}`)}">
            <div class="g-band" style="left:${at(NEAR_LIMIT_PCT)};width:calc(${at(100)} - ${at(NEAR_LIMIT_PCT)})" data-tip="${esc(GLOSS.margin[1])}"></div>
            <div class="g-seg g-bg" style="width:${at(bgPct)}" data-tip="${esc(`Already in the air (illustrative background): ${ug(s.background_ugm3)}`)}"></div>
            <div class="g-seg g-plant" style="left:${at(bgPct)};width:${at(Math.max(0, p - bgPct))}" data-tip="${esc(`The plant adds ${ug(s.total_ugm3 - s.background_ugm3)} at the worst spot`)}"></div>
            <div class="g-limit" style="left:${at(100)}" data-tip="${esc(`Federal limit (NAAQS): ${s.limit_ppb} ppb = ${ug(s.limit_ugm3)}`)}"></div>
        </div>
        <div class="g-scale"><span style="left:0">0%</span><span class="g-near" style="left:${at(NEAR_LIMIT_PCT)}">${NEAR_LIMIT_PCT}%</span>
            <span class="g-lim" style="left:${at(100)}">Limit</span></div>
    </div>`;
}

function answerSentence(r, pol) {
    const k = worstOf(r), s = r[k], p = Math.round(s.percent_of_limit), lvl = levelOf(s);
    const where = `${km(s.distance_m)} ${COMPASS_WORDS[compassIdx(s.direction_deg)]} of the stack`;
    const lead = `At the worst spot, ${where}, the air reaches ${p}% of the ${LIMIT_POL[pol] ?? pol} ${LIMIT_NAME[k]}, counting pollution already in the air.`;
    if (lvl === 'ok') return `${lead} That leaves ${100 - p}% headroom.`;
    if (lvl === 'warn') return `${lead} Still within the limit, but past the ${NEAR_LIMIT_PCT}% safety margin: a worse weather year or higher background could tip it over.`;
    return `${lead} That is over the limit: as modelled, this would need a taller stack or lower emissions to pass.`;
}

// Today's operation means every model input matches the baseline, not just the fuel mix.
function compareInputs(data) {
    const flat = ({stack, stack_key, ...rest}) => ({...stack, ...rest});
    const s = flat(data.scenario.inputs), b = flat(data.baseline.inputs), p = WI.presets[pollutant()][fuel()];
    const preset = {...b, emission_rate_gs: p.emission_rate_gs, temperature_k: p.exit_temperature_k};
    const isToday = Object.keys(b).every(k => s[k] === b[k]);
    const adjusted = Object.keys(preset).some(k => s[k] !== preset[k]);
    return {isToday, label: `${mixShort(fuel())}${adjusted ? ' (adjusted)' : ''}`};
}

function renderAnswer(data) {
    const pol = pollutant(), r = data.scenario, base = data.baseline, {isToday, label} = compareInputs(data);
    const forWhat = `<p class="ans-for">Answer for <b>${esc(label)}</b> · ${term(POL_TERM[pol], `${esc(POL_NAME[pol])} (${polShort(pol)}${POL_NOTE[pol] ?? ''})`)}</p>`;
    if (!r.certified) {
        const unavailable = r.status === 'unavailable';
        $('wi-answer').innerHTML = `<div class="card answer neutral"><div class="ans-main">${forWhat}
            <div class="ans-status neutral">${ic('neutral')}${unavailable ? 'Not precomputed' : 'Outside this demo\'s scope'}</div>
            <ul class="issues">${r.issues.map(i => `<li>${esc(i)}</li>`).join('')}</ul>
            ${unavailable ? '' : '<p class="muted">No number is shown rather than a wrong one. This demo covers one stack on flat, rural ground with no building close enough to cause building wake. A full study handles these.</p>'}
        </div></div>`;
        return;
    }
    const k = worstOf(r), s = r[k], lvl = levelOf(s), p = s.percent_of_limit;
    let side;
    if (isToday || !base.certified) {
        side = `<div class="today"><p class="k">Compared with today</p><p class="today-v">This is today's operation.</p>
            <p class="muted small">Pick an alternative-fuel mix above to see how the answer changes.</p></div>`;
    } else {
        const bs = base[worstOf(base)], bl = levelOf(bs), d = Math.round(p) - Math.round(bs.percent_of_limit);
        side = `<div class="today"><p class="k">Today · ${esc(mixShort(WI.defaults.fuel_mix))}</p>
            <p class="today-v"><b>${Math.round(bs.percent_of_limit)}%</b> ${badge(bl, LEVEL_TEXT[bl])}</p>
            <p class="delta">${d > 0 ? `<span aria-hidden="true">▲</span> ${d} points closer to the limit than today`
                : d < 0 ? `<span aria-hidden="true">▼</span> ${-d} points further from the limit than today` : 'Same as today'}</p></div>`;
    }
    const inp = r.inputs;
    side += `<dl class="facts">
        <dt>${term('worst', 'Worst spot')}</dt><dd>${km(s.distance_m)} ${compass(s.direction_deg)} of the stack</dd>
        <dt>Plant's share there</dt><dd>${ug(s.total_ugm3 - s.background_ugm3)}</dd>
        <dt>${term('background', 'Already in the air')} <span class="tag">Illustrative</span></dt><dd>${ug(s.background_ugm3)}</dd>
        <dt>Emission rate <span class="tag">Illustrative</span></dt><dd>${gs(inp.emission_rate_gs)}</dd>
    </dl>`;
    $('wi-answer').innerHTML = `<div class="card answer ${lvl}">
        <div class="ans-main">${forWhat}
            <div class="ans-row">
                <div class="ans-status ${lvl}">${ic(lvl)}${LEVEL_TEXT[lvl]}</div>
                <div class="ans-big"><span class="pct">${Math.round(p)}<small>%</small></span>
                    <span class="of">of the ${term('naaqs', `federal ${LIMIT_POL[pol] ?? pol} ${LIMIT_NAME[k]}`)}<br><span class="muted">at the worst spot around the plant</span></span></div>
            </div>
            <p class="ans-say">${esc(answerSentence(r, pol))}</p>
            <div class="gauges">${gauge(pol, 'one_hour', r.one_hour)}${gauge(pol, 'annual', r.annual)}</div>
            <p class="g-key"><span><i class="k-bg"></i>Already in the air</span><span><i class="k-plant"></i>Added by the plant</span>
                <span><i class="k-band"></i>${term('margin', `Close-to-limit margin (${NEAR_LIMIT_PCT}–100%, our screening choice)`)}</span></p>
        </div>
        <aside class="ans-side">${side}</aside>
    </div>`;
}

function renderTrust() {
    const o = OVERVIEW, c = caseTotals(o), p = o.provenance, match = allMatch(o);
    const item = (cls, t, d) => `<div class="trust-item">${ic(cls)}<div><b>${t}</b><p>${d}</p></div></div>`;
    const checked = STATIC?.ci ? `Last check: ${extLink(STATIC.ci.run_url, esc(longDate(STATIC.ci.completed_at)))}, passed.` : '';
    $('trust-grid').innerHTML = [
        item(match ? 'ok' : 'bad', match ? `Same answers as EPA's own model` : 'Not all EPA test cases match yet',
            `On ${match ? 'all' : `${c.passing} of`} ${c.total} of EPA's official ${term('aermod', 'AERMOD')} test cases, this model matches EPA's Fortran code, compiled here from EPA's source, hour by hour at every location, and agrees with EPA's published results where EPA ships them.`),
        item(o.certified ? 'ok' : STATIC ? 'bad' : 'neutral', o.certified ? 'Checked automatically, every time' : 'Automatic check not passed here',
            `Every change to the model reruns all of EPA's test cases on an ${term('ci', 'independent build server')}. ${checked}`),
        p.ok && p.python_files
            ? item('ok', 'Nothing tuned by hand',
                'Every line of the model was written by AI from EPA\'s source code and traced to the request that wrote it. The pass mark is locked.')
            : item('bad', 'Model trace check failed',
                'Some model files do not trace to a recorded AI request, so a hand edit cannot be ruled out. The pass mark is still locked.'),
    ].join('');
}

const PALETTE = [[246, 244, 240], [214, 223, 232], [166, 189, 210], [104, 141, 176], [52, 95, 135], [24, 49, 74]];
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
    let s = `<svg class="chart polar" viewBox="0 0 ${S} ${S + 44}" role="img" aria-label="${esc(title)}"><text class="title" x="${cx}" y="14" text-anchor="middle">${esc(title)}</text>`;
    if (!r.certified) {
        const msg = r.status === 'unavailable' ? 'not precomputed' : 'outside the demo scope';
        return s + `<circle class="map-empty" cx="${cx}" cy="${cy}" r="${R}"/>
            <text class="faint" x="${cx}" y="${cy}" text-anchor="middle" font-size="14">${msg}</text></svg>`;
    }
    const vals = r.field[metric];
    r.field.x.forEach((x, i) => {
        const y = r.field.y[i], d = Math.hypot(x, y), ang = Math.atan2(x, y);
        const ring = dists.findIndex(v => Math.abs(v - d) < 1);
        const [ri, ro] = [r0 + ring * w, r0 + (ring + 1) * w];
        const [a, b] = [ang - half, ang + half];
        const p = [pt(ro, a), pt(ro, b), pt(ri, b), pt(ri, a)];
        const where = `${km(d)} ${compass((ang * 180 / Math.PI + 360) % 360)}`;
        s += `<path d="M${p[0]} A${ro},${ro} 0 0 1 ${p[1]} L${p[2]} A${ri},${ri} 0 0 0 ${p[3]} Z" fill="${color(vals[i] / vmax)}" stroke="#fff" stroke-width="0.6" data-tip="${esc(`${where} from the stack: ${ug(vals[i])}`)}"/>`;
    });
    dists.forEach((d, k) => {
        if (k % 2 === 1 || k === dists.length - 1) s += `<text class="ring" x="${cx + 3}" y="${cy - (r0 + (k + 1) * w) + 10}" font-size="9">${km(d)}</text>`;
    });
    const best = vals.indexOf(Math.max(...vals));
    const bx = r.field.x[best], by = r.field.y[best], bd = Math.hypot(bx, by);
    const bring = dists.findIndex(v => Math.abs(v - bd) < 1);
    const [mx, my] = pt(r0 + (bring + 0.5) * w, Math.atan2(bx, by));
    s += `<circle cx="${mx}" cy="${my}" r="8" fill="none" stroke="#fff" stroke-width="4.5"/>`;
    s += `<circle class="hot" cx="${mx}" cy="${my}" r="8" fill="none" stroke-width="2.5" data-tip="${esc(`Highest: ${ug(vals[best])}`)}"/>`;
    s += `<rect class="stack-mark" x="${cx - 4}" y="${cy - 4}" width="8" height="8" data-tip="Kiln stack"/>`;
    for (const [lab, ang] of [['N', 0], ['E', 90], ['S', 180], ['W', 270]]) {
        const [tx, ty] = pt(R + 14, ang * Math.PI / 180);
        s += `<text class="compass" x="${tx}" y="${ty + 4}" font-size="12" text-anchor="middle">${lab}</text>`;
    }
    s += `<text x="${cx}" y="${S + 38}" font-size="12" text-anchor="middle">Highest: ${ug(vals[best])}, ${km(bd)} ${compass((Math.atan2(bx, by) * 180 / Math.PI + 360) % 360)} (circled)</text>`;
    return s + '</svg>';
}

function renderMaps(data) {
    const metric = $('wi-metric').value;
    const shown = [data.baseline, data.scenario].filter(r => r.certified);
    const vmax = Math.max(1e-12, ...shown.flatMap(r => r.field[metric]));
    const what = {annual: 'yearly average', one_hour: '1-hour design value', max_1h: 'single worst hour'}[metric];
    const legend = `<div class="map-legend"><span>0</span><span class="ramp" style="background:linear-gradient(90deg,${PALETTE.map(c => `rgb(${c.join(',')})`).join(',')})"></span>
        <span>${ug(vmax)}</span></div>`;
    const {isToday, label} = compareInputs(data);
    $('wi-maps').innerHTML = polarMap(`Today: ${mixShort(WI.defaults.fuel_mix)}`, data.baseline, metric, vmax)
        + (isToday ? '' : polarMap(`With ${label}`, data.scenario, metric, vmax));
    $('wi-maps').classList.toggle('single', isToday);
    $('wi-map-note').innerHTML = legend + `<p class="muted small">The plant's share only (no background), ${esc(what)}, in ${term('ugm3', 'µg/m³')}; both maps share one colour scale.
        Each cell is one point: ${WI.receptors.directions} directions, rings at ${WI.receptors.distances_m.map(km).join(', ')} (drawn evenly spaced). Hover a cell for its value.</p>`;
}

function renderStandards() {
    const pol = pollutant(), std = WI.naaqs[pol], mw = WI.pollutants[pol].molecular_weight;
    const line = (name, s) => `<li><b>${name}: ${s.ppb} ppb = ${s.limit_ugm3.toFixed(1)} µg/m³</b> (${esc(s.form)}). ${esc(s.cite)}.</li>`;
    $('wi-standards').innerHTML = `<h3 class="sub-h">The federal limits for ${esc(POL_NAME[pol] ?? pol)} ${tip(GLOSS.naaqs[1])}</h3><ul>
        ${line('1-hour', std.one_hour)}${line('Yearly average', std.annual)}</ul>
        <p>Source: US EPA, <a href="https://www.epa.gov/criteria-air-pollutants/naaqs-table" target="_blank" rel="noopener">NAAQS Table</a>
        (40 CFR part 50). Converted with µg/m³ = ppb × ${mw} / 24.45 (25 °C, 1 atm, 40 CFR 50.3).
        Emission rates convert at 1 g/s = ${LB_PER_HR_PER_G_S.toFixed(2)} lb/hr.</p>
        <h3 class="sub-h">Method and caveats</h3><ul>
        <li>Design value: the 1-hour standard's form is a percentile of daily maximum 1-hour values averaged over 3 years. With one year of
            weather this demo uses the ${ordinal(std.one_hour.rank)}-highest daily maximum at each receptor (the high-${ordinal(std.one_hour.rank)}-high),
            the single-year stand-in used in EPA modelling practice. The yearly standard is compared with the one-year mean.</li>
        <li>% of limit = (plant's design value + background) / NAAQS at the worst receptor. "Close to limit" (amber) marks ${NEAR_LIMIT_PCT}% or more:
            a screening margin chosen for this tool, not a regulatory threshold.</li>
        ${pol === 'NOX' ? '<li>All NOx is treated as NO₂ (EPA Tier 1 full conversion), which overstates NO₂.</li>' : ''}
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
        the same Python model scored on the <a href="#proof" data-go="proof">Proof page</a>. Each stack is ${fmt(p.hours)} hours of weather
        (${fmt(p.excluded_hours)} calm or missing) on ${WI.receptors.directions * WI.receptors.distances_m.length} receptors,
        run once at 1 g/s (${Math.round(p.seconds)} s for this stack) and scaled to the chosen emission rate.` +
        (p.port_is_current ? '' : ` ${badge('bad', 'computed with a different model version: rerun make whatif')}`) + coverage;
}

// --- navigation ------------------------------------------------------------------------
const loaders = {whatif: loadWhatif, proof: loadProof, port: loadPort, about: loadAbout};
function show(screen, {scroll = false} = {}) {
    document.body.dataset.screen = screen;
    document.querySelectorAll('.nav a').forEach(a => a.dataset.go === screen
        ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'));
    document.querySelectorAll('.screen').forEach(s => s.classList.toggle('active', s.dataset.screen === screen));
    if (location.hash.slice(1) !== screen) history.replaceState(null, '', `#${screen}`);
    if (scroll) window.scrollTo({top: 0});
    const el = $(`sec-${screen}`);
    el.querySelector(':scope > .error')?.remove();
    return loaders[screen]().catch(err => {
        console.error(err);
        el.insertAdjacentHTML('afterbegin', `<div class="error">${ic('bad')}<span><b>Could not load this section:</b> ${esc(err.message)}. ${STATIC
            ? 'The static export may be incomplete: rerun <code>make export-static</code>.' : 'Is <code>server.py</code> still running?'}</span></div>`);
    });
}
document.addEventListener('click', e => {
    const a = e.target.closest?.('[data-go]');
    if (!a || e.ctrlKey || e.metaKey || e.shiftKey) return;
    e.preventDefault();
    show(a.dataset.go, {scroll: true});
});
let resizeTimer = null;
window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
        const screen = document.querySelector('.screen.active')?.dataset.screen;
        if (screen === 'proof' || screen === 'port') show(screen);
    }, 250);
});
window.addEventListener('hashchange', () => loaders[location.hash.slice(1)] && show(location.hash.slice(1), {scroll: true}));
show(loaders[location.hash.slice(1)] ? location.hash.slice(1) : 'whatif');

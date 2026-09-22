/* Cement ESG Control Tower -- frontend logic.
 * Talks only to the Flask API in app/ui/server.py, which in turn only
 * ever calls app.agent.orchestrator.run. This file renders whatever comes
 * back; it never fabricates a number or a status itself.
 */

const el = (id) => document.getElementById(id);

const STATUS_PILL = {
  "Compliant": "pill-good", "Within Target": "pill-good", "Clean": "pill-good", "Applicable": "pill-good",
  "Potential Gap": "pill-warn", "Evidence Missing": "pill-warn", "Evidence Outdated": "pill-warn",
  "Issues Flagged": "pill-warn", "Missing Data": "pill-warn", "Mixed": "pill-warn", "Data Missing": "pill-warn",
  "Data Conflict": "pill-bad", "Conflicts Found": "pill-bad", "Conflicting": "pill-bad", "Exceeds Target": "pill-bad",
  "Human Review Required": "pill-review", "Cannot Determine": "pill-review",
  "Not Applicable": "pill-neutral", "No Target Configured": "pill-neutral",
};

const PRIORITY_PILL = { "Critical": "pill-bad", "High": "pill-warn", "Medium": "pill-review", "Low": "pill-neutral" };

const CATEGORY_COLOR_VAR = {
  "Carbon": "--warn", "Energy": "--accent", "Evidence": "--review", "Data Quality": "--good",
};

function pillClass(status) {
  return STATUS_PILL[status] || "pill-neutral";
}

function scoreColor(score) {
  if (score >= 80) return "var(--good)";
  if (score >= 60) return "var(--accent)";
  if (score >= 40) return "var(--warn)";
  return "var(--bad)";
}

function scoreBandLabel(score) {
  if (score >= 80) return "Strong";
  if (score >= 60) return "Adequate";
  if (score >= 40) return "Needs Attention";
  return "Weak";
}

// --------------------------------------------------------------- bootstrap

let CONFIG = null;
let lastRunPlant = null;
let lastRunPeriod = null;

async function init() {
  const res = await fetch("/api/config");
  CONFIG = await res.json();

  const plantSelect = el("plantSelect");
  CONFIG.plants.forEach((p) => plantSelect.add(new Option(p, p)));

  const periodSelect = el("periodSelect");
  CONFIG.periods.forEach((p) => periodSelect.add(new Option(p, p)));
  periodSelect.value = CONFIG.default_period;

  const typeSelect = el("typeSelect");
  CONFIG.assessment_types.forEach((t) => typeSelect.add(new Option(t.label, t.id)));

  const chipsWrap = el("exampleChips");
  CONFIG.example_queries.forEach((q) => {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.type = "button";
    chip.textContent = q.length > 42 ? q.slice(0, 40) + "…" : q;
    chip.title = q;
    chip.addEventListener("click", () => { el("queryInput").value = q; });
    chipsWrap.appendChild(chip);
  });

  el("runBtn").addEventListener("click", runFromControls);
  el("askBtn").addEventListener("click", runFromQuery);
  el("downloadReportBtn").addEventListener("click", downloadReport);
}

// ----------------------------------------------------------------- running

function setBusy(isBusy) {
  el("runBtn").disabled = isBusy;
  el("askBtn").disabled = isBusy;
  el("runBtn").querySelector(".run-btn-label").textContent = isBusy ? "Running…" : "Run Assessment";
  el("runBtn").querySelector(".spinner").hidden = !isBusy;

  const dot = el("systemDot");
  dot.className = "status-dot" + (isBusy ? " busy" : " online");
  el("systemStatusText").textContent = isBusy ? "Agent Working…" : "Agent Online";

  if (isBusy) {
    el("activityFeed").innerHTML = '<div class="activity-item busy">Planning and selecting tools…</div>';
  }
}

function runFromControls() {
  const assessmentType = el("typeSelect").value;
  const plant = el("plantSelect").value;
  const period = el("periodSelect").value;
  // Always driven by the Plant/Period/Assessment Type controls, never by
  // whatever text happens to be sitting in the separate "Ask the Agent"
  // box -- that box is runFromQuery()'s (the Ask button's) input, not
  // this one's. Reading it here used to let stale leftover text (e.g.
  // from an earlier typed question, or an example chip) silently override
  // a freshly-changed Plant/Period selection.
  execute({ query: "", plant, period, assessment_type: assessmentType });
}

function runFromQuery() {
  const query = el("queryInput").value.trim();
  if (!query) {
    el("queryInput").focus();
    return;
  }
  // Deliberately no plant/period hint here: a typed query is a genuine
  // natural-language request, and the agent's own text parsing (which
  // plant/period it names, or its own reasonable default) should decide --
  // silently overriding "Plant C" in the typed text with a stale "Plant A"
  // left over in the header dropdown would contradict what the user just
  // asked. The header controls stay meaningful for "Run Assessment" below,
  // which builds its own query text from them.
  execute({ query, plant: null, period: null, assessment_type: el("typeSelect").value });
}

async function execute(payload) {
  setBusy(true);
  hide(el("errorBanner"));
  hide(el("incompleteBanner"));

  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      showError(data.message || `Request failed (HTTP ${res.status}).`);
      return;
    }

    lastRunPlant = data.objective ? data.objective.plant : payload.plant;
    lastRunPeriod = data.objective ? data.objective.reporting_period : payload.period;
    render(data);
  } catch (err) {
    showError("Connection error: could not reach the agent service. " + err.message);
  } finally {
    setBusy(false);
  }
}

function showError(message) {
  const banner = el("errorBanner");
  banner.textContent = "⚠ " + message;
  banner.hidden = false;
  el("systemDot").className = "status-dot error";
  el("systemStatusText").textContent = "Agent Error";
  el("activityFeed").innerHTML = '<p class="placeholder">No activity to show.</p>';
}

function hide(node) { node.hidden = true; }
function show(node) { node.hidden = false; }

// ---------------------------------------------------------------- render

function render(data) {
  el("emptyState").hidden = true;

  if (data.status === "incomplete_missing_data") {
    const banner = el("incompleteBanner");
    banner.textContent = "⚠ " + data.final_answer;
    show(banner);
  }

  renderActivity(data.activity_trace);
  renderQueryResult(data);
  renderGuardrails(data);

  if (data.readiness_score) {
    renderReadinessHero(data.readiness_score);
    renderGaps(data.key_gaps);
    renderRootCause(data.root_cause_analysis);
    renderActions(data.priority_actions);
    renderDataQuality(data.data_quality_issues, data.kpi_dashboard, data.evidence_status);
  } else {
    hide(el("readinessHero"));
    hide(el("gapsPanel"));
    hide(el("rootCausePanel"));
    hide(el("actionsPanel"));
    hide(el("dataQualityPanel"));
  }
}

function renderActivity(trace) {
  const feed = el("activityFeed");
  feed.innerHTML = "";
  if (!trace || trace.length === 0) {
    feed.innerHTML = '<p class="placeholder">No activity recorded for this run.</p>';
    return;
  }
  trace.forEach((entry, i) => {
    const item = document.createElement("div");
    item.className = "activity-item " + entry.status;
    item.style.animationDelay = (i * 40) + "ms";
    item.innerHTML = `<span class="activity-symbol">${escapeHtml(entry.symbol)}</span><span class="activity-text">${escapeHtml(entry.description)}</span>`;
    feed.appendChild(item);
  });
}

function renderQueryResult(data) {
  const panel = el("queryResultPanel");
  if (!data.objective) { hide(panel); return; }

  el("queryEcho").textContent = data.objective.raw_query;
  el("queryAnswer").textContent = data.final_answer || "No answer produced.";

  const pill = el("queryConfidencePill");
  pill.textContent = "Confidence: " + data.confidence;
  pill.className = "pill " + (data.confidence === "High" ? "pill-good" : data.confidence === "Medium" ? "pill-warn" : "pill-bad");

  const assumptionsWrap = el("queryAssumptions");
  assumptionsWrap.innerHTML = "";
  (data.objective.assumptions || []).forEach((a) => {
    const p = document.createElement("p");
    p.className = "assumption-item";
    p.textContent = "Assumption: " + a;
    assumptionsWrap.appendChild(p);
  });

  show(panel);
}

const GUARDRAIL_SEVERITY_PILL = { CRITICAL: "pill-bad", HIGH: "pill-bad", MEDIUM: "pill-warn", LOW: "pill-neutral" };

function guardrailBarColor(pct) {
  if (pct === null || pct === undefined) return "var(--text-faint)";
  if (pct >= 90) return "var(--good)";
  if (pct >= 60) return "var(--warn)";
  return "var(--bad)";
}

function renderGuardrails(data) {
  const panel = el("guardrailsPanel");
  const g = data.guardrails;
  if (!g) { hide(panel); return; }

  const pill = el("guardrailsReviewPill");
  pill.textContent = "Human Review: " + (g.human_review_required ? "YES" : "NO");
  pill.className = "pill " + (g.human_review_required ? "pill-warn" : "pill-good");

  const bars = [
    ["Data Integrity", g.data_integrity_pct],
    ["Evidence Coverage", g.evidence_coverage_pct],
    ["Regulatory Source Validity", g.regulatory_source_validity_pct],
    ["Calculation Validation", g.calculation_validation_pct],
  ];
  const barsWrap = el("guardrailBars");
  barsWrap.innerHTML = "";
  bars.forEach(([label, pct]) => {
    const item = document.createElement("div");
    item.className = "guardrail-bar-item";
    const display = pct === null || pct === undefined ? "n/a" : pct.toFixed(0) + "%";
    item.innerHTML = `
      <div class="guardrail-bar-label"><span>${escapeHtml(label)}</span><b>${escapeHtml(display)}</b></div>
      <div class="guardrail-bar-track"><div class="guardrail-bar-fill" style="width:${pct || 0}%; background:${guardrailBarColor(pct)}"></div></div>
    `;
    barsWrap.appendChild(item);
  });

  const eventsWrap = el("guardrailEvents");
  const events = g.recent_events || [];
  if (events.length === 0) {
    eventsWrap.innerHTML = '<h3>Recent Guardrail Events</h3><p class="guardrail-events-empty">No guardrail interventions this run -- every check passed cleanly.</p>';
  } else {
    const rows = events.slice().reverse().map((e) => `
      <div class="guardrail-event-row">
        <span class="pill ${GUARDRAIL_SEVERITY_PILL[e.severity] || "pill-neutral"}">${escapeHtml(e.guardrail)}</span>
        <span class="ge-metric">${escapeHtml(e.metric || "")}</span>
        <span class="ge-reason">${escapeHtml(e.reason)}</span>
      </div>
    `).join("");
    eventsWrap.innerHTML = `<h3>Recent Guardrail Events (${g.total_events})</h3>${rows}`;
  }

  show(panel);
}

function renderReadinessHero(score) {
  const hero = el("readinessHero");
  const overall = score.overall_score;
  const color = scoreColor(overall);

  el("scoreRing").style.setProperty("--pct", overall);
  el("scoreRing").style.setProperty("--ring-color", color);
  el("scoreNumber").textContent = Math.round(overall);
  el("scoreBand").textContent = scoreBandLabel(overall);

  const grid = el("categoryGrid");
  grid.innerHTML = "";
  score.breakdown.forEach((cat) => {
    const card = document.createElement("div");
    card.className = "category-card";
    const colorVar = CATEGORY_COLOR_VAR[cat.category] || "--accent";
    card.innerHTML = `
      <div class="cat-top">
        <span class="cat-name">${escapeHtml(cat.category)}</span>
        <span class="cat-weight">weight ${Math.round(cat.weight * 100)}%</span>
      </div>
      <div class="cat-score" style="color:${scoreColor(cat.score)}">${cat.score.toFixed(1)}</div>
      <div class="cat-bar-track"><div class="cat-bar-fill" style="width:${Math.min(cat.score,100)}%; background:var(${colorVar})"></div></div>
      <div class="cat-reason">${escapeHtml(cat.reason)}</div>
    `;
    grid.appendChild(card);
  });

  const dlBtn = el("downloadReportBtn");
  if (lastRunPlant && lastRunPeriod) {
    dlBtn.hidden = false;
  }

  show(hero);
}

function renderGaps(gaps) {
  const panel = el("gapsPanel");
  const tbody = document.querySelector("#gapsTable tbody");
  tbody.innerHTML = "";

  if (!gaps || gaps.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="dq-empty">No gaps identified for this assessment.</td></tr>';
    el("gapsCount").textContent = "0 gaps";
    show(panel);
    return;
  }

  el("gapsCount").textContent = gaps.length + (gaps.length === 1 ? " gap" : " gaps");
  gaps.forEach((g) => {
    const tr = document.createElement("tr");
    let metricText = "—";
    if (g.metric) {
      const actual = typeof g.actual_value === "number" ? g.actual_value.toFixed(3) : "?";
      metricText = g.target_value != null ? `${g.metric}: ${actual} vs. target ${g.target_value}` : `${g.metric}: ${actual}`;
    }
    tr.innerHTML = `
      <td>${escapeHtml(g.requirement_id)}<div class="rc-node-detail">${escapeHtml(g.regulation)}</div></td>
      <td><span class="pill ${pillClass(g.status)}">${escapeHtml(g.status)}</span></td>
      <td class="wrap-col mono">${escapeHtml(metricText)}</td>
      <td>${g.priority_band ? `<span class="pill ${PRIORITY_PILL[g.priority_band] || "pill-neutral"}">${escapeHtml(g.priority_band)}</span>` : "—"}</td>
      <td class="wrap-col">${escapeHtml((g.notes || []).join(" ")) || "—"}</td>
    `;
    tbody.appendChild(tr);
  });
  show(panel);
}

function renderActions(actions) {
  const panel = el("actionsPanel");
  const tbody = document.querySelector("#actionsTable tbody");
  tbody.innerHTML = "";

  if (!actions || actions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="dq-empty">No corrective actions required.</td></tr>';
    el("actionsCount").textContent = "0 actions";
    show(panel);
    return;
  }

  el("actionsCount").textContent = actions.length + (actions.length === 1 ? " action" : " actions");
  actions.forEach((a) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="wrap-col">${escapeHtml(a.corrective_action)}</td>
      <td>${escapeHtml(a.suggested_owner)}</td>
      <td><span class="pill ${PRIORITY_PILL[a.priority] || "pill-neutral"}">${escapeHtml(a.priority)}</span></td>
      <td class="mono">${escapeHtml(a.suggested_timeline)}</td>
      <td class="wrap-col">${escapeHtml(a.business_impact.summary)}</td>
      <td><span class="pill pill-neutral">Open</span></td>
    `;
    tbody.appendChild(tr);
  });
  show(panel);
}

function shortFactLabel(text) {
  // Facts read like "Plant B's specific_thermal_energy_..._clinker increased
  // 9.9% across the configured periods." -- the character class must
  // include the apostrophe or the match (and the later strip of "Plant
  // B's ") silently starts one character too late.
  const m = text.match(/([A-Za-z0-9_' ]+?) (increased|decreased) ([\d.]+)%/);
  if (m) {
    const metric = m[1].replace(/^.*'s\s+/, "").replace(/_/g, " ");
    const arrow = m[2] === "increased" ? "↑" : "↓";
    return `${metric} ${arrow} ${m[3]}%`;
  }
  return text.length > 46 ? text.slice(0, 44) + "…" : text;
}

function renderRootCause(sections) {
  const panel = el("rootCausePanel");
  const wrap = el("rootCauseFlow");
  wrap.innerHTML = "";

  if (!sections || sections.length === 0) {
    wrap.innerHTML = '<p class="dq-empty">No gap in this period met the threshold for an autonomous root-cause investigation.</p>';
    show(panel);
    return;
  }

  sections.forEach((rc) => {
    const block = document.createElement("div");
    block.className = "rc-block";

    const trendClass = rc.trend === "increasing" ? "rc-trend-up" : "rc-trend-down";
    const trendArrow = rc.trend === "increasing" ? "↑" : rc.trend === "decreasing" ? "↓" : "→";
    const title = document.createElement("div");
    title.className = "rc-title";
    title.innerHTML = `${escapeHtml(rc.metric.replace(/_/g, " "))} <span class="${trendClass}">${trendArrow} ${escapeHtml(rc.trend)}</span> &mdash; investigation for ${escapeHtml(rc.requirement_id)}`;
    block.appendChild(title);

    const flow = document.createElement("div");
    flow.className = "rc-flow";

    const nodes = [
      ...rc.facts.map((f) => ({ kind: "fact", text: f, confidence: null })),
      ...rc.hypotheses.map((h) => ({ kind: "hypothesis", text: h.statement, confidence: h.confidence })),
    ];

    nodes.forEach((node, i) => {
      if (i > 0) {
        const arrow = document.createElement("div");
        arrow.className = "rc-arrow";
        arrow.textContent = "→";
        flow.appendChild(arrow);
      }
      const div = document.createElement("div");
      div.className = "rc-node is-" + node.kind;
      const kindLabel = node.kind === "fact" ? "Fact" : `Hypothesis · ${node.confidence} confidence`;
      div.innerHTML = `
        <div class="rc-node-kind">${escapeHtml(kindLabel)}</div>
        <div class="rc-node-title">${escapeHtml(shortFactLabel(node.text))}</div>
        <div class="rc-node-detail">${escapeHtml(node.text)}</div>
      `;
      flow.appendChild(div);
    });

    block.appendChild(flow);
    wrap.appendChild(block);
  });

  show(panel);
}

function renderDataQuality(dq, kpis, evidence) {
  const panel = el("dataQualityPanel");
  const grid = el("dataQualityGrid");
  grid.innerHTML = "";

  const overallPill = el("dataQualityOverallPill");
  overallPill.textContent = dq.overall;
  overallPill.className = "pill " + pillClass(dq.overall);

  const missing = [...dq.missing_domains];
  (kpis || []).forEach((k) => { if (k.data_status === "missing") missing.push(k.name); });

  const conflicting = [...dq.conflicting_domains, ...dq.duplicate_documents.map((d) => `Duplicate document: ${d}`)];

  const outdated = [];
  (evidence || []).forEach((e) => (e.outdated_evidence || []).forEach((doc) => outdated.push(`${e.requirement_id}: ${doc}`)));

  grid.appendChild(dqCard("Missing Data", missing));
  grid.appendChild(dqCard("Conflicting Data", conflicting));
  grid.appendChild(dqCard("Outdated Evidence", outdated));

  show(panel);
}

function dqCard(title, items) {
  const card = document.createElement("div");
  card.className = "dq-card";
  const list = items.length
    ? items.map((i) => `<li>${escapeHtml(i)}</li>`).join("")
    : '<li class="dq-empty">None detected</li>';
  card.innerHTML = `<h3>${escapeHtml(title)}</h3><ul>${list}</ul>`;
  return card;
}

function downloadReport() {
  if (!lastRunPlant || !lastRunPeriod) return;
  const url = `/api/report.pdf?plant=${encodeURIComponent(lastRunPlant)}&period=${encodeURIComponent(lastRunPeriod)}`;
  window.open(url, "_blank");
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

init();

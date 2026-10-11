const METRICS_URL = "data/metrics.json";

function hoursLabel(h) {
  if (h == null || Number.isNaN(h)) return "—";
  if (h < 48) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
}

function pctLabel(v) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v.toFixed(1)}%`;
}

function numLabel(v, digits = 0) {
  if (v == null || Number.isNaN(v)) return "—";
  return digits ? v.toFixed(digits) : String(Math.round(v));
}

function periodsForGranularity(data, granularity) {
  const map = data[granularity];
  if (!map) return [];
  return Object.keys(map).sort();
}

function filterPeriods(periods, granularity) {
  if (granularity === "month") return periods.slice(-36);
  if (granularity === "quarter") return periods.slice(-16);
  return periods;
}

function seriesFromPeriods(map, periods, key) {
  return periods.map((p) => {
    const row = map[p];
    if (!row) return null;
    const v = row[key];
    return v == null ? null : v;
  });
}

let charts = {};

function destroyCharts() {
  Object.values(charts).forEach((c) => c.destroy());
  charts = {};
}

function renderQueueChart(history) {
  const el = document.getElementById("chart-queue");
  if (!el || !history || !history.length) return;
  const labels = history.map((h) => (h.at || "").slice(0, 10));
  const common = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { labels: { color: "#8b9cb3" } } },
    scales: {
      x: { ticks: { color: "#8b9cb3", maxRotation: 45, minRotation: 45 }, grid: { color: "#2d3a4d" } },
      y: { ticks: { color: "#8b9cb3" }, grid: { color: "#2d3a4d" } },
    },
  };
  charts.queue = new Chart(el, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Open PRs",
          data: history.map((h) => h.open_prs_total),
          borderColor: "#4dabf7",
          yAxisID: "y",
          tension: 0.2,
        },
        {
          label: "Open age p90 (days)",
          data: history.map((h) => (h.open_age_p90_h == null ? null : h.open_age_p90_h / 24)),
          borderColor: "#ffa94d",
          yAxisID: "y1",
          tension: 0.2,
        },
      ],
    },
    options: {
      ...common,
      scales: {
        ...common.scales,
        y: { ...common.scales.y, position: "left", title: { display: true, text: "Count", color: "#8b9cb3" } },
        y1: {
          position: "right",
          ticks: { color: "#8b9cb3" },
          grid: { drawOnChartArea: false },
          title: { display: true, text: "Days", color: "#8b9cb3" },
        },
      },
    },
  });
}

function renderCharts(periods, map) {
  const labels = periods;
  const common = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { labels: { color: "#8b9cb3" } } },
    scales: {
      x: { ticks: { color: "#8b9cb3", maxRotation: 45, minRotation: 45 }, grid: { color: "#2d3a4d" } },
      y: { ticks: { color: "#8b9cb3" }, grid: { color: "#2d3a4d" } },
    },
  };

  const apprP50 = seriesFromPeriods(map, periods, "approval_to_merge_p50_h").map((h) => (h == null ? null : h / 24));
  const apprP90 = seriesFromPeriods(map, periods, "approval_to_merge_p90_h").map((h) => (h == null ? null : h / 24));
  charts.approval = new Chart(document.getElementById("chart-approval"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Approval → merge p50 (days)", data: apprP50, borderColor: "#51cf66", tension: 0.2 },
        { label: "Approval → merge p90 (days)", data: apprP90, borderColor: "#2f9e44", tension: 0.2 },
      ],
    },
    options: common,
  });

  const leadP50Days = seriesFromPeriods(map, periods, "lead_p50_h").map((h) => (h == null ? null : h / 24));
  const leadP90Days = seriesFromPeriods(map, periods, "lead_p90_h").map((h) => (h == null ? null : h / 24));
  charts.lead = new Chart(document.getElementById("chart-lead"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Lead p50 (days)", data: leadP50Days, borderColor: "#63e6be", tension: 0.2, yAxisID: "y" },
        { label: "Lead p90 (days)", data: leadP90Days, borderColor: "#ffa94d", tension: 0.2, yAxisID: "y" },
        {
          label: "Merges >14d %",
          data: seriesFromPeriods(map, periods, "slow_merge_pct_14d"),
          borderColor: "#ff8787",
          tension: 0.2,
          yAxisID: "y1",
        },
      ],
    },
    options: {
      ...common,
      scales: {
        ...common.scales,
        y: { ...common.scales.y, position: "left" },
        y1: {
          position: "right",
          ticks: { color: "#8b9cb3" },
          grid: { drawOnChartArea: false },
          suggestedMin: 0,
          suggestedMax: 100,
        },
      },
    },
  });

  const revP50Days = seriesFromPeriods(map, periods, "review_p50_h").map((h) => (h == null ? null : h / 24));
  const postP50Days = seriesFromPeriods(map, periods, "post_review_p50_h").map((h) => (h == null ? null : h / 24));
  charts.review = new Chart(document.getElementById("chart-review"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "1st human review p50 (days)", data: revP50Days, borderColor: "#74c0fc", tension: 0.2 },
        { label: "After human review → merge p50 (days)", data: postP50Days, borderColor: "#ff922b", tension: 0.2 },
      ],
    },
    options: common,
  });

  charts.ci = new Chart(document.getElementById("chart-ci"), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Head CI pass rate %",
          data: seriesFromPeriods(map, periods, "ci_pass_rate_pct"),
          borderColor: "#ffd43b",
          tension: 0.2,
          spanGaps: true,
        },
        {
          label: "Fail on last 15 commits %",
          data: seriesFromPeriods(map, periods, "ci_fail_before_merge_pct"),
          borderColor: "#fa5252",
          tension: 0.2,
          spanGaps: true,
        },
      ],
    },
    options: {
      ...common,
      scales: { ...common.scales, y: { ...common.scales.y, suggestedMin: 0, suggestedMax: 100 } },
    },
  });

  charts.merged = new Chart(document.getElementById("chart-merged"), {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Merged", data: seriesFromPeriods(map, periods, "merged"), backgroundColor: "#4dabf7" },
        { label: "Opened", data: seriesFromPeriods(map, periods, "opened"), backgroundColor: "#495057" },
      ],
    },
    options: common,
  });

  charts.contributors = new Chart(document.getElementById("chart-contributors"), {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Unique merge authors",
          data: seriesFromPeriods(map, periods, "unique_contributors"),
          backgroundColor: "#63e6be",
        },
      ],
    },
    options: { ...common, plugins: { ...common.plugins, legend: { display: false } } },
  });

  charts.size = new Chart(document.getElementById("chart-size"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Changed files p50", data: seriesFromPeriods(map, periods, "files_p50"), borderColor: "#da77f2", tension: 0.2 },
        { label: "Changed files p90", data: seriesFromPeriods(map, periods, "files_p90"), borderColor: "#ae3ec9", tension: 0.2 },
      ],
    },
    options: common,
  });

  charts.quality = new Chart(document.getElementById("chart-quality"), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Revert rate %",
          data: seriesFromPeriods(map, periods, "revert_rate_pct"),
          borderColor: "#ff8787",
          tension: 0.2,
        },
        {
          label: "Flow ratio (merged÷opened ×100)",
          data: seriesFromPeriods(map, periods, "flow_ratio").map((v) => (v == null ? null : v * 100)),
          borderColor: "#91a7ff",
          tension: 0.2,
          yAxisID: "y1",
        },
      ],
    },
    options: {
      ...common,
      scales: {
        ...common.scales,
        y: { ...common.scales.y, position: "left", suggestedMin: 0 },
        y1: {
          position: "right",
          ticks: { color: "#8b9cb3" },
          grid: { drawOnChartArea: false },
          suggestedMin: 0,
          suggestedMax: 120,
        },
      },
    },
  });

  charts.issues = new Chart(document.getElementById("chart-issues"), {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Issues closed", data: seriesFromPeriods(map, periods, "issues_closed"), backgroundColor: "#228be6" },
      ],
    },
    options: { ...common, plugins: { ...common.plugins, legend: { display: false } } },
  });
}

function renderTable(periods, map) {
  const tbody = document.querySelector("#metrics-table tbody");
  tbody.innerHTML = "";
  for (const p of periods) {
    const r = map[p];
    if (!r) continue;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p}</td>
      <td>${r.merged ?? "—"}</td>
      <td>${r.opened ?? "—"}</td>
      <td>${numLabel(r.flow_ratio, 2)}</td>
      <td>${hoursLabel(r.lead_p50_h)}</td>
      <td>${pctLabel(r.slow_merge_pct_14d)}</td>
      <td>${hoursLabel(r.approval_to_merge_p50_h)}</td>
      <td>${pctLabel(r.ci_fail_before_merge_pct)}</td>
      <td>${pctLabel(r.ci_pass_rate_pct)}</td>
    `;
    tbody.appendChild(tr);
  }
}

function refresh(data) {
  destroyCharts();
  const granularity = document.getElementById("granularity").value;
  const map = data[granularity];
  const periods = filterPeriods(periodsForGranularity(data, granularity), granularity);
  renderCharts(periods, map);
  renderQueueChart(data.open_pr_history);
  renderTable(periods, map);
}

async function main() {
  const meta = document.getElementById("meta");
  const snap = document.getElementById("snapshot");
  try {
    const res = await fetch(METRICS_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    meta.textContent = `${data.repository} · ${data.total_merged_prs.toLocaleString()} merged PRs · updated ${data.generated_at}`;
    if (data.snapshot) {
      const s = data.snapshot;
      snap.textContent =
        `Now: ${s.open_prs_total} open PRs · age p50 ${hoursLabel(s.open_age_p50_h)} · ` +
        `${s.open_prs_stale_30d_in_sample} stale >30d (sample ${s.open_prs_sample_size})`;
    }
    document.getElementById("granularity").addEventListener("change", () => refresh(data));
    refresh(data);
  } catch (e) {
    meta.textContent = "Failed to load metrics.";
    document.getElementById("load-error").textContent = String(e);
  }
}

main();

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

function renderCharts(periods, map) {
  destroyCharts();
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

  const leadP50Days = seriesFromPeriods(map, periods, "lead_p50_h").map((h) => (h == null ? null : h / 24));
  const leadP90Days = seriesFromPeriods(map, periods, "lead_p90_h").map((h) => (h == null ? null : h / 24));
  charts.lead = new Chart(document.getElementById("chart-lead"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Lead p50 (days)", data: leadP50Days, borderColor: "#63e6be", tension: 0.2 },
        { label: "Lead p90 (days)", data: leadP90Days, borderColor: "#ffa94d", tension: 0.2 },
      ],
    },
    options: common,
  });

  const revP50Days = seriesFromPeriods(map, periods, "review_p50_h").map((h) => (h == null ? null : h / 24));
  const postP50Days = seriesFromPeriods(map, periods, "post_review_p50_h").map((h) => (h == null ? null : h / 24));
  charts.review = new Chart(document.getElementById("chart-review"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "1st review p50 (days)", data: revP50Days, borderColor: "#74c0fc", tension: 0.2 },
        { label: "After review → merge p50 (days)", data: postP50Days, borderColor: "#ff922b", tension: 0.2 },
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
          label: "CI pass rate %",
          data: seriesFromPeriods(map, periods, "ci_pass_rate_pct"),
          borderColor: "#ffd43b",
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
          label: "Merge/flow ratio (merged÷opened)",
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
      <td>${r.unique_contributors ?? "—"}</td>
      <td>${hoursLabel(r.lead_p50_h)}</td>
      <td>${hoursLabel(r.post_review_p50_h)}</td>
      <td>${numLabel(r.files_p50, 1)}</td>
      <td>${numLabel(r.reviews_per_pr_p50, 1)}</td>
      <td>${pctLabel(r.revert_rate_pct)}</td>
      <td>${r.issues_closed ?? "—"}</td>
      <td>${pctLabel(r.ci_pass_rate_pct)}</td>
    `;
    tbody.appendChild(tr);
  }
}

function refresh(data) {
  const granularity = document.getElementById("granularity").value;
  const map = data[granularity];
  const periods = filterPeriods(periodsForGranularity(data, granularity), granularity);
  renderCharts(periods, map);
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
      snap.textContent =
        `Now: ${data.snapshot.open_prs_total} open PRs · ` +
        `${data.snapshot.open_prs_stale_30d_in_sample} stale >30d (in sample of ${data.snapshot.open_prs_sample_size})`;
    }
    document.getElementById("granularity").addEventListener("change", () => refresh(data));
    refresh(data);
  } catch (e) {
    meta.textContent = "Failed to load metrics.";
    document.getElementById("load-error").textContent = String(e);
  }
}

main();

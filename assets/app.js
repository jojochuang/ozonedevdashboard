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

function periodsForGranularity(data, granularity) {
  const map = data[granularity];
  if (!map) return [];
  return Object.keys(map).sort();
}

function filterPeriods(periods, granularity) {
  if (granularity === "month") {
    return periods.slice(-36);
  }
  if (granularity === "quarter") {
    return periods.slice(-16);
  }
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
      datasets: [{ label: "Merged PRs", data: seriesFromPeriods(map, periods, "merged"), backgroundColor: "#4dabf7" }],
    },
    options: { ...common, plugins: { ...common.plugins, legend: { display: false } } },
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
  const revP90Days = seriesFromPeriods(map, periods, "review_p90_h").map((h) => (h == null ? null : h / 24));
  charts.review = new Chart(document.getElementById("chart-review"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "1st review p50 (days)", data: revP50Days, borderColor: "#74c0fc", tension: 0.2 },
        { label: "1st review p90 (days)", data: revP90Days, borderColor: "#b197fc", tension: 0.2 },
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
      scales: {
        ...common.scales,
        y: { ...common.scales.y, suggestedMin: 0, suggestedMax: 100 },
      },
    },
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
      <td>${r.merged}</td>
      <td>${hoursLabel(r.lead_p50_h)}</td>
      <td>${hoursLabel(r.lead_p90_h)}</td>
      <td>${hoursLabel(r.review_p50_h)}</td>
      <td>${hoursLabel(r.review_p90_h)}</td>
      <td>${pctLabel(r.review_coverage_pct)}</td>
      <td>${pctLabel(r.ci_pass_rate_pct)}</td>
      <td>${r.ci_known_n ?? 0}</td>
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
  try {
    const res = await fetch(METRICS_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    meta.textContent = `${data.repository} · ${data.total_merged_prs.toLocaleString()} merged PRs · updated ${data.generated_at}`;
    document.getElementById("granularity").addEventListener("change", () => refresh(data));
    refresh(data);
  } catch (e) {
    meta.textContent = "Failed to load metrics.";
    document.getElementById("load-error").textContent = String(e);
  }
}

main();

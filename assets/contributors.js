const DATA_URL = "data/contributor_activity.json";

let chartSubmitted;
let chartReviewed;
let chartMerged;

function monthKeys(byMonth) {
  return Object.keys(byMonth).sort();
}

function quarterKeys(byMonth) {
  const set = new Set();
  for (const mo of monthKeys(byMonth)) {
    const y = mo.slice(0, 4);
    const q = Math.floor((parseInt(mo.slice(5, 7), 10) - 1) / 3) + 1;
    set.add(`${y}-Q${q}`);
  }
  return [...set].sort();
}

function yearKeys(byMonth) {
  const set = new Set();
  for (const mo of monthKeys(byMonth)) {
    set.add(mo.slice(0, 4));
  }
  return [...set].sort();
}

function monthsInQuarter(qKey) {
  const y = qKey.slice(0, 4);
  const q = parseInt(qKey.slice(-1), 10);
  const start = (q - 1) * 3 + 1;
  return [0, 1, 2].map((i) => `${y}-${String(start + i).padStart(2, "0")}`);
}

function monthsInYear(yKey) {
  return Array.from({ length: 12 }, (_, i) => `${yKey}-${String(i + 1).padStart(2, "0")}`);
}

function mergeLoginMaps(byMonth, monthList, field) {
  const out = {};
  for (const mo of monthList) {
    const part = byMonth[mo];
    if (!part) continue;
    const m = part[field] || {};
    for (const [login, n] of Object.entries(m)) {
      out[login] = (out[login] || 0) + n;
    }
  }
  return out;
}

function aggregatePeriod(byMonth, granularity, periodKey) {
  let months;
  if (granularity === "month") {
    months = [periodKey];
  } else if (granularity === "quarter") {
    months = monthsInQuarter(periodKey);
  } else {
    months = monthsInYear(periodKey);
  }
  return {
    submitted: mergeLoginMaps(byMonth, months, "submitted_by_login"),
    reviewed: mergeLoginMaps(byMonth, months, "reviews_by_login"),
    mergedBy: mergeLoginMaps(byMonth, months, "merges_by_login"),
  };
}

function periodOptions(byMonth, granularity) {
  if (granularity === "month") return monthKeys(byMonth);
  if (granularity === "quarter") return quarterKeys(byMonth);
  return yearKeys(byMonth);
}

function buildRows(agg) {
  const logins = new Set([
    ...Object.keys(agg.submitted),
    ...Object.keys(agg.reviewed),
    ...Object.keys(agg.mergedBy),
  ]);
  return [...logins].map((login) => {
    const submitted = agg.submitted[login] || 0;
    const reviewed = agg.reviewed[login] || 0;
    const mergedBy = agg.mergedBy[login] || 0;
    return { login, submitted, reviewed, mergedBy, total: submitted + reviewed + mergedBy };
  });
}

function topN(map, n) {
  return Object.entries(map)
    .sort((a, b) => b[1] - a[1])
    .slice(0, n);
}

function destroyCharts() {
  [chartSubmitted, chartReviewed, chartMerged].forEach((c) => c && c.destroy());
  chartSubmitted = chartReviewed = chartMerged = null;
}

function renderCharts(agg) {
  destroyCharts();
  const common = {
    indexAxis: "y",
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: "#8b9cb3" }, grid: { color: "#2d3a4d" } },
      y: { ticks: { color: "#8b9cb3" }, grid: { color: "#2d3a4d" } },
    },
  };
  const mk = (id, map, color) => {
    const top = topN(map, 15);
    return new Chart(document.getElementById(id), {
      type: "bar",
      data: {
        labels: top.map((t) => t[0]),
        datasets: [{ data: top.map((t) => t[1]), backgroundColor: color }],
      },
      options: common,
    });
  };
  chartSubmitted = mk("chart-submitted", agg.submitted, "#4dabf7");
  chartReviewed = mk("chart-reviewed", agg.reviewed, "#63e6be");
  chartMerged = mk("chart-merged-by", agg.mergedBy, "#ffa94d");
}

let sortKey = "reviewed";
let sortDir = -1;

function renderTable(rows) {
  const sorted = [...rows].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    return sortDir * (av - bv);
  });
  const tbody = document.querySelector("#contrib-table tbody");
  tbody.innerHTML = "";
  sorted.forEach((r, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td>${r.login}</td>
      <td>${r.submitted}</td>
      <td>${r.reviewed}</td>
      <td>${r.mergedBy}</td>
      <td>${r.total}</td>
    `;
    tbody.appendChild(tr);
  });
  document.querySelectorAll("#contrib-table th[data-sort]").forEach((th) => {
    const k = th.dataset.sort;
    th.setAttribute("aria-sort", k === sortKey ? (sortDir < 0 ? "descending" : "ascending") : "none");
  });
}

function refresh(data) {
  const byMonth = data.by_month || {};
  const granularity = document.getElementById("granularity").value;
  const periodSelect = document.getElementById("period");
  const periods = periodOptions(byMonth, granularity);
  if (!periods.length) return;
  if (!periods.includes(periodSelect.value)) {
    periodSelect.value = periods[periods.length - 1];
  }
  const agg = aggregatePeriod(byMonth, granularity, periodSelect.value);
  const rows = buildRows(agg);
  renderCharts(agg);
  renderTable(rows);
  const sum = (m) => Object.values(m).reduce((a, b) => a + b, 0);
  document.getElementById("period-summary").textContent =
    `Period ${periodSelect.value}: ${sum(agg.submitted)} submitted · ${sum(agg.reviewed)} reviews · ${sum(agg.mergedBy)} merges by`;
}

function populatePeriodSelect(data, granularity) {
  const byMonth = data.by_month || {};
  const select = document.getElementById("period");
  const current = select.value;
  const periods = periodOptions(byMonth, granularity);
  select.innerHTML = "";
  for (const p of periods) {
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = p;
    select.appendChild(opt);
  }
  if (periods.includes(current)) {
    select.value = current;
  } else if (periods.length) {
    select.value = periods[periods.length - 1];
  }
}

async function main() {
  const meta = document.getElementById("meta");
  try {
    const res = await fetch(DATA_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    meta.textContent =
      `${data.repository} · ${data.total_prs_scanned?.toLocaleString() ?? "?"} PRs scanned · updated ${data.generated_at}`;
    const trunc = document.getElementById("trunc-note");
    if (data.reviews_truncated_pr_count > 0) {
      trunc.textContent =
        `Note: ${data.reviews_truncated_pr_count} PRs had >50 reviews; counts may be slightly low.`;
    }
    const onChange = () => {
      populatePeriodSelect(data, document.getElementById("granularity").value);
      refresh(data);
    };
    document.getElementById("granularity").addEventListener("change", onChange);
    document.getElementById("period").addEventListener("change", () => refresh(data));
    document.querySelectorAll("#contrib-table th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const k = th.dataset.sort;
        if (sortKey === k) sortDir *= -1;
        else {
          sortKey = k;
          sortDir = -1;
        }
        refresh(data);
      });
    });
    populatePeriodSelect(data, document.getElementById("granularity").value);
    refresh(data);
  } catch (e) {
    meta.textContent = "Failed to load contributor activity.";
    document.getElementById("load-error").textContent = String(e);
  }
}

main();

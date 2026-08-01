const charts = {};

function formatTimestamp(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function average(values) {
  return values.length
    ? values.reduce((sum, value) => sum + value, 0) / values.length
    : 0;
}

function percentageChange(first, last) {
  if (!Number.isFinite(first) || first === 0 || !Number.isFinite(last)) {
    return null;
  }
  return ((last - first) / Math.abs(first)) * 100;
}

function trendText(change, positiveIsGood) {
  if (change === null || Math.abs(change) < 0.01) return "Stable";
  const direction = change > 0 ? "increased" : "decreased";
  const favourable = positiveIsGood ? change > 0 : change < 0;
  const prefix = favourable ? "Improved" : "Review";
  return `${prefix}: ${direction} ${Math.abs(change).toFixed(1)}%`;
}

function colours() {
  const styles = getComputedStyle(document.documentElement);
  return {
    primary: styles.getPropertyValue("--accent").trim() || "#4f8cff",
    secondary: styles.getPropertyValue("--warning").trim() || "#f5a623",
    grid: styles.getPropertyValue("--border").trim() || "rgba(128,128,128,.2)",
    text: styles.getPropertyValue("--muted").trim() || "#8b95a7",
  };
}

function lineChart(id, labels, values, label, suffix) {
  const canvas = document.getElementById(id);
  if (!canvas || typeof Chart === "undefined") return;
  if (charts[id]) charts[id].destroy();

  const palette = colours();
  charts[id] = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label,
        data: values,
        borderColor: palette.primary,
        backgroundColor: `${palette.primary}22`,
        fill: true,
        tension: 0.28,
        pointRadius: values.length > 60 ? 0 : 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      plugins: { legend: { display: false } },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: palette.text, maxTicksLimit: 8 },
        },
        y: {
          grid: { color: palette.grid },
          ticks: {
            color: palette.text,
            callback(value) {
              return `${value}${suffix}`;
            },
          },
        },
      },
    },
  });
}

function restartChart(labels, values) {
  const id = "restart-chart";
  const canvas = document.getElementById(id);
  if (!canvas || typeof Chart === "undefined") return;
  if (charts[id]) charts[id].destroy();

  const palette = colours();
  charts[id] = new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Container restarts",
        data: values,
        backgroundColor: palette.secondary,
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: palette.text, maxTicksLimit: 8 },
        },
        y: {
          beginAtZero: true,
          ticks: { color: palette.text, precision: 0 },
          grid: { color: palette.grid },
        },
      },
    },
  });
}

function renderMetrics(data) {
  const scores = data.score || [];
  const latency = data.latency || [];
  const restarts = data.restarts || [];
  const labels = data.labels || [];

  const latestScore = scores.at(-1);
  const latestLatency = latency.at(-1);

  document.getElementById("latest-score").textContent =
    Number.isFinite(latestScore) ? `${latestScore}%` : "—";
  document.getElementById("score-change").textContent =
    trendText(percentageChange(scores[0], latestScore), true);
  document.getElementById("average-latency").textContent =
    latency.length ? `${average(latency).toFixed(3)}s` : "—";
  document.getElementById("latency-change").textContent =
    trendText(percentageChange(latency[0], latestLatency), false);
  document.getElementById("maximum-restarts").textContent =
    String(restarts.length ? Math.max(...restarts) : 0);
  document.getElementById("snapshot-count").textContent =
    String(labels.length);
  document.getElementById("history-freshness").textContent =
    labels.length
      ? `Latest: ${formatTimestamp(labels.at(-1))}`
      : "No snapshots available";
}

function renderCharts(data) {
  const labels = (data.labels || []).map(formatTimestamp);
  lineChart("platform-score-chart", labels, data.score || [], "Score", "%");
  lineChart("latency-chart", labels, data.latency || [], "Latency", "s");
  restartChart(labels, data.restarts || []);
}

function renderTable(items) {
  const body = document.getElementById("history-table-body");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="5">No snapshots available.</td></tr>';
    return;
  }

  body.innerHTML = items.slice(0, 12).map(item => `
    <tr>
      <td>${formatTimestamp(item.recorded_at)}</td>
      <td>${item.platform_score}%</td>
      <td>${Number(item.health_latency_seconds).toFixed(3)}s</td>
      <td>${item.container_restarts}</td>
      <td><code>${item.git_revision}</code></td>
    </tr>
  `).join("");
}

async function getJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function loadHistory() {
  const message = document.getElementById("history-message");
  const hours = document.getElementById("history-range").value;
  message.textContent = "Refreshing platform history…";

  try {
    const [chartData, recentData] = await Promise.all([
      getJson(`/api/v1/history/chart?hours=${encodeURIComponent(hours)}`),
      getJson("/api/v1/history?limit=12"),
    ]);

    renderMetrics(chartData);
    renderCharts(chartData);
    renderTable(recentData.items || []);
    message.textContent =
      `Loaded ${chartData.labels?.length || 0} snapshots from the last ${hours} hours.`;
  } catch (error) {
    message.textContent = `Unable to load history: ${error.message}`;
  }
}

document.getElementById("history-refresh").addEventListener("click", loadHistory);
document.getElementById("history-range").addEventListener("change", loadHistory);

loadHistory();
setInterval(loadHistory, 300000);

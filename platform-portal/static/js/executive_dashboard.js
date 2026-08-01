function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatTimestamp(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function signed(value, digits = 0, suffix = "") {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  const prefix = numeric > 0 ? "+" : "";
  return `${prefix}${numeric.toFixed(digits)}${suffix}`;
}

function renderRecommendations(items) {
  const container = document.getElementById("executive-recommendations");

  if (!items.length) {
    container.innerHTML = `
      <article class="executive-recommendation executive-info">
        <h3>No recommendations</h3>
        <p>The platform is operating within expected thresholds.</p>
      </article>
    `;
    return;
  }

  container.innerHTML = items.map(item => `
    <article class="executive-recommendation executive-${escapeHtml(item.severity)}">
      <span>${escapeHtml(item.severity)}</span>
      <h3>${escapeHtml(item.title)}</h3>
      <p>${escapeHtml(item.detail)}</p>
      <small>${escapeHtml(item.action)}</small>
    </article>
  `).join("");
}

function renderDashboard(data) {
  const latest = data.latest;

  if (!latest) {
    document.getElementById("executive-message").textContent =
      "No platform snapshots are available.";
    renderRecommendations(data.recommendations || []);
    return;
  }

  document.getElementById("executive-score").textContent =
    `${latest.platform_score}%`;
  document.getElementById("executive-score-trend").textContent =
    `${signed(data.trend?.score_change, 0, " points")} over selected range`;
  document.getElementById("executive-status").textContent =
    data.status || "unknown";
  document.getElementById("executive-generated").textContent =
    `Latest snapshot: ${formatTimestamp(latest.recorded_at)}`;

  document.getElementById("executive-nodes").textContent =
    latest.node_readiness;
  document.getElementById("executive-replicas").textContent =
    latest.replica_readiness;
  document.getElementById("executive-gitops").textContent =
    latest.argo_sync_status;
  document.getElementById("executive-gitops-health").textContent =
    `Health: ${latest.argo_health_status}`;

  document.getElementById("executive-http").textContent =
    `HTTP ${latest.http_status}`;
  document.getElementById("executive-latency").textContent =
    `Latency: ${Number(latest.health_latency_seconds).toFixed(3)}s`;

  document.getElementById("executive-restarts").textContent =
    String(latest.container_restarts);
  document.getElementById("executive-restart-trend").textContent =
    `${signed(data.trend?.restart_change)} over selected range`;

  document.getElementById("executive-security").textContent =
    String(latest.security_pass_count);
  document.getElementById("executive-findings").textContent =
    `${latest.warning_count} warnings, ${latest.failure_count} failures`;

  document.getElementById("trend-score-change").textContent =
    signed(data.trend?.score_change, 0, " points");
  document.getElementById("trend-latency-change").textContent =
    signed(data.trend?.latency_change, 3, "s");
  document.getElementById("trend-restart-change").textContent =
    signed(data.trend?.restart_change);

  document.getElementById("executive-revision").textContent =
    latest.git_revision;
  document.getElementById("executive-branch").textContent =
    latest.git_branch;
  document.getElementById("executive-recorded").textContent =
    formatTimestamp(latest.recorded_at);

  renderRecommendations(data.recommendations || []);
}

async function loadExecutiveDashboard() {
  const message = document.getElementById("executive-message");
  const hours = document.getElementById("executive-range").value;

  message.textContent = "Refreshing platform overview…";

  try {
    const response = await fetch(
      `/api/v1/executive?hours=${encodeURIComponent(hours)}`,
      { cache: "no-store" },
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    renderDashboard(data);
    message.textContent = `Overview refreshed for the last ${hours} hours.`;
  } catch (error) {
    message.textContent = `Unable to load overview: ${error.message}`;
  }
}

document
  .getElementById("executive-refresh")
  .addEventListener("click", loadExecutiveDashboard);

document
  .getElementById("executive-range")
  .addEventListener("change", loadExecutiveDashboard);

loadExecutiveDashboard();
setInterval(loadExecutiveDashboard, 300000);

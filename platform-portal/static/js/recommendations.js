function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderSummary(data) {
  document.getElementById("recommendation-status").textContent =
    data.status || "unknown";
  document.getElementById("critical-count").textContent =
    data.summary?.critical ?? 0;
  document.getElementById("warning-count").textContent =
    data.summary?.warning ?? 0;
  document.getElementById("info-count").textContent =
    data.summary?.info ?? 0;
}

function renderRecommendations(items) {
  const container = document.getElementById("recommendation-list");

  container.innerHTML = items.map(item => `
    <article class="recommendation-card recommendation-${escapeHtml(item.severity)}">
      <header>
        <span class="recommendation-badge">${escapeHtml(item.severity)}</span>
        <span class="recommendation-category">${escapeHtml(item.category)}</span>
      </header>
      <h2>${escapeHtml(item.title)}</h2>
      <p>${escapeHtml(item.detail)}</p>
      <div class="recommendation-action">
        <strong>Recommended action</strong>
        <span>${escapeHtml(item.action)}</span>
      </div>
    </article>
  `).join("");
}

async function loadRecommendations() {
  const message = document.getElementById("recommendation-message");
  const hours = document.getElementById("recommendation-range").value;

  message.textContent = "Analysing platform history…";

  try {
    const response = await fetch(
      `/api/v1/recommendations?hours=${encodeURIComponent(hours)}`,
      { cache: "no-store" },
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();

    renderSummary(data);
    renderRecommendations(data.recommendations || []);
    message.textContent =
      `Analysis complete for the last ${hours} hours.`;
  } catch (error) {
    message.textContent =
      `Unable to load recommendations: ${error.message}`;
  }
}

document
  .getElementById("recommendation-refresh")
  .addEventListener("click", loadRecommendations);

document
  .getElementById("recommendation-range")
  .addEventListener("change", loadRecommendations);

loadRecommendations();
setInterval(loadRecommendations, 300000);

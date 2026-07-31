async function loadStatus() {
  const response = await fetch("/api/status", { cache: "no-store" });
  if (!response.ok) throw new Error(`Status request failed: ${response.status}`);
  return response.json();
}

function setField(name, value) {
  const element = document.querySelector(`[data-field="${name}"]`);
  if (element) element.textContent = value;
}

function formatDate(value) {
  try { return new Date(value).toLocaleString(); }
  catch { return value; }
}

function renderChecks(checks, areas = null) {
  const body = document.getElementById("checks");
  if (!body) return;
  const selected = areas ? checks.filter(check => areas.includes(check.area)) : checks;
  body.innerHTML = selected.map(check => `
    <tr>
      <td>${check.area}</td>
      <td>${check.name}</td>
      <td><span class="badge ${check.status}">${check.status}</span></td>
      <td>${check.detail}</td>
    </tr>
  `).join("");
}

function renderPage(data) {
  const page = document.body.dataset.page;
  document.getElementById("generated").textContent = `Generated ${formatDate(data.generated_at)}`;

  if (page === "overview") {
    setField("score", `${data.score}%`);
    setField("pass", data.summary.pass);
    setField("warn", data.summary.warn);
    setField("fail", data.summary.fail);
    renderChecks(data.checks);
  }

  if (page === "infrastructure") {
    setField("nodes", `${data.platform.nodes_ready}/${data.platform.nodes_total}`);
    setField("replicas", `${data.workload.ready_replicas}/${data.workload.desired_replicas}`);
    setField("service", data.networking.service_type);
    setField("policies", data.networking.network_policy_count);
    renderChecks(data.checks, ["Platform", "AKS", "Workload", "Networking", "Scheduling"]);
  }

  if (page === "security") {
    setField("nonroot", data.security.run_as_non_root ? "Enforced" : "Review");
    setField("privilege", data.security.privilege_escalation_disabled ? "Disabled" : "Review");
    setField("seccomp", data.security.seccomp_runtime_default ? "RuntimeDefault" : "Review");
    setField("secret", data.identity.external_secret_ready ? "Ready" : "Review");
    renderChecks(data.checks, ["Security", "Identity", "Networking"]);
  }

  if (page === "performance") {
    setField("http", data.availability.http_code);
    setField("latency", `${data.availability.health_latency_seconds.toFixed(3)}s`);
    setField("restarts", data.workload.container_restarts);
    setField("hpa", data.resilience.hpa_exists ? "Configured" : "Missing");
    renderChecks(data.checks, ["Availability", "Performance", "Workload", "Resilience"]);
  }

  if (page === "gitops") {
    setField("sync", data.gitops.sync_status);
    setField("argohealth", data.gitops.health_status);
    setField("branch", data.git.branch);
    setField("revision", data.git.revision);
    const details = document.getElementById("git-details");
    details.innerHTML = `
      <div class="key">Working tree</div><div>${data.git.clean ? "Clean" : "Local changes"}</div>
      <div class="key">Last commit</div><div>${data.git.last_commit_message}</div>
      <div class="key">Commit date</div><div>${formatDate(data.git.last_commit_date)}</div>
    `;
    renderChecks(data.checks, ["GitOps", "Repository"]);
  }

  if (page === "observability") {
    setField("metrics", data.observability.metrics_api_available ? "Available" : "Review");
    setField("servicemonitor", data.observability.service_monitor_present ? "Present" : "Review");
    setField("healthtelemetry", data.availability.http_code === "200" ? "Healthy" : "Failed");
    setField("latencysample", `${data.availability.health_latency_seconds.toFixed(3)}s`);
    renderChecks(data.checks, ["Observability", "Availability", "Performance"]);
  }

  if (page === "resilience") {
    setField("rhpa", data.resilience.hpa_exists ? "Configured" : "Missing");
    setField("pdb", data.resilience.pdb_exists ? "Configured" : "Missing");
    setField("startup", data.resilience.startup_probe ? "Configured" : "Missing");
    setField("spread", data.resilience.topology_spread ? "Configured" : "Missing");
    renderChecks(data.checks, ["Resilience", "Reliability", "Scheduling", "Workload"]);
  }
}

loadStatus().then(renderPage).catch(error => {
  document.getElementById("generated").textContent = error.message;
});

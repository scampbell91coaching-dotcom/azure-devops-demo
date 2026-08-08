async function loadStatus() {
  const endpoint = document.body.dataset.page === "observability"
    ? "/api/v1/observability"
    : "/api/v1/platform";
  const response = await fetch(endpoint, { cache: "no-store" });
  if (!response.ok) throw new Error(`Status request failed: ${response.status}`);
  const data = await response.json();
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new Error("Status response was malformed");
  }
  return data;
}

function setField(name, value) {
  const element = document.querySelector(`[data-field="${name}"]`);
  if (element) element.textContent = value;
}

function formatDate(value) {
  if (!value) return "status collection unavailable";
  try { return new Date(value).toLocaleString(); }
  catch { return value; }
}

function renderChecks(checks, areas = null) {
  const body = document.getElementById("checks");
  if (!body) return;
  body.replaceChildren();
  const validChecks = Array.isArray(checks)
    ? checks.filter(check => check && typeof check === "object")
    : [];
  const selected = areas
    ? validChecks.filter(check => areas.includes(check.area))
    : validChecks;
  if (!selected.length) {
    const row = body.insertRow();
    const cell = row.insertCell();
    cell.colSpan = 4;
    cell.textContent = "No controls were reported.";
    return;
  }
  selected.forEach(check => {
    const row = body.insertRow();
    [check.area, check.name].forEach(value => {
      row.insertCell().textContent = displayValue(value);
    });
    const statusCell = row.insertCell();
    const badge = document.createElement("span");
    const status = displayValue(check.status, "UNKNOWN").toUpperCase();
    badge.className = `badge ${status}`;
    badge.textContent = status;
    statusCell.appendChild(badge);
    row.insertCell().textContent = displayValue(check.detail);
  });
}

function objectValue(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function displayValue(value, fallback = "Unknown") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function numberValue(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function dependencyLabel(dependency) {
  const status = objectValue(dependency).status;
  return ["AVAILABLE", "DEGRADED", "UNAVAILABLE", "UNKNOWN", "NOT_CONFIGURED"].includes(status)
    ? status.replace("_", " ")
    : "UNKNOWN";
}

function renderPage(data) {
  const page = document.body.dataset.page;
  const generated = document.getElementById("generated");
  if (generated) generated.textContent = `Generated ${formatDate(data.generated_at)}`;

  const summary = objectValue(data.summary);
  const platform = objectValue(data.platform);
  const workload = objectValue(data.workload);
  const networking = objectValue(data.networking);
  const security = objectValue(data.security);
  const identity = objectValue(data.identity);
  const availability = objectValue(data.availability);
  const resilience = objectValue(data.resilience);
  const gitops = objectValue(data.gitops);
  const git = objectValue(data.git);
  const checks = Array.isArray(data.checks) ? data.checks : [];

  if (page === "overview") {
    setField("score", numberValue(data.score) === null ? "Unknown" : `${data.score}%`);
    setField("pass", displayValue(summary.pass));
    setField("warn", displayValue(summary.warn));
    setField("fail", displayValue(summary.fail));
    renderChecks(checks);
  }

  if (page === "infrastructure") {
    setField("nodes", `${displayValue(platform.nodes_ready)}/${displayValue(platform.nodes_total)}`);
    setField("replicas", `${displayValue(workload.ready_replicas)}/${displayValue(workload.desired_replicas)}`);
    setField("service", displayValue(networking.service_type));
    setField("policies", displayValue(networking.network_policy_count));
    renderChecks(checks, ["Platform", "AKS", "Workload", "Networking", "Scheduling"]);
  }

  if (page === "security") {
    setField("nonroot", security.run_as_non_root === true ? "Enforced" : security.run_as_non_root === false ? "Review" : "Unknown");
    setField("privilege", security.privilege_escalation_disabled === true ? "Disabled" : security.privilege_escalation_disabled === false ? "Review" : "Unknown");
    setField("seccomp", security.seccomp_runtime_default === true ? "RuntimeDefault" : security.seccomp_runtime_default === false ? "Review" : "Unknown");
    setField("secret", identity.external_secret_ready === true ? "Ready" : identity.external_secret_ready === false ? "Review" : "Unknown");
    renderChecks(checks, ["Security", "Identity", "Networking"]);
  }

  if (page === "performance") {
    const latency = numberValue(availability.health_latency_seconds);
    setField("http", displayValue(availability.http_code));
    setField("latency", latency === null ? "Unknown" : `${latency.toFixed(3)}s`);
    setField("restarts", displayValue(workload.container_restarts));
    setField("hpa", resilience.hpa_exists === true ? "Configured" : resilience.hpa_exists === false ? "Missing" : "Unknown");
    renderChecks(checks, ["Availability", "Performance", "Workload", "Resilience"]);
  }

  if (page === "gitops") {
    setField("sync", displayValue(gitops.sync_status));
    setField("argohealth", displayValue(gitops.health_status));
    setField("branch", displayValue(git.branch));
    setField("revision", displayValue(git.revision));
    const details = document.getElementById("git-details");
    if (details) {
      details.replaceChildren();
      [["Working tree", git.clean === true ? "Clean" : git.clean === false ? "Local changes" : "Unknown"],
       ["Last commit", displayValue(git.last_commit_message)],
       ["Commit date", formatDate(git.last_commit_date)]].forEach(([key, value]) => {
        const keyElement = document.createElement("div");
        keyElement.className = "key";
        keyElement.textContent = key;
        const valueElement = document.createElement("div");
        valueElement.textContent = value;
        details.append(keyElement, valueElement);
      });
    }
    renderChecks(checks, ["GitOps", "Repository"]);
  }

  if (page === "observability") {
    const telemetry = objectValue(data.telemetry);
    const latencySample = objectValue(telemetry.latency_sample);
    const seconds = numberValue(latencySample.seconds);
    setField("metrics", dependencyLabel(telemetry.metrics_api));
    setField("servicemonitor", dependencyLabel(telemetry.service_monitor));
    setField("healthtelemetry", dependencyLabel(telemetry.health));
    setField("latencysample", seconds === null
      ? dependencyLabel(latencySample)
      : `${seconds.toFixed(3)}s (${dependencyLabel(latencySample)})`);
    renderChecks(data.controls);
  }

  if (page === "resilience") {
    setField("rhpa", resilience.hpa_exists === true ? "Configured" : resilience.hpa_exists === false ? "Missing" : "Unknown");
    setField("pdb", resilience.pdb_exists === true ? "Configured" : resilience.pdb_exists === false ? "Missing" : "Unknown");
    setField("startup", resilience.startup_probe === true ? "Configured" : resilience.startup_probe === false ? "Missing" : "Unknown");
    setField("spread", resilience.topology_spread === true ? "Configured" : resilience.topology_spread === false ? "Missing" : "Unknown");
    renderChecks(checks, ["Resilience", "Reliability", "Scheduling", "Workload"]);
  }
}

function renderFailure(error) {
  const message = error instanceof Error ? error.message : "Status request failed";
  const generated = document.getElementById("generated");
  if (generated) generated.textContent = message;
  if (document.body.dataset.page === "observability") {
    ["metrics", "servicemonitor", "healthtelemetry", "latencysample"].forEach(name => {
      setField(name, "UNAVAILABLE");
    });
    renderChecks([{area: "Portal", name: "Telemetry request", status: "FAIL", detail: message}]);
  }
}

loadStatus().then(renderPage).catch(renderFailure);

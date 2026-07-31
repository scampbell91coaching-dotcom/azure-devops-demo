#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-$HOME/azure-devops-demo}"
PORTAL_DIR="$REPO/portal"
DATA_FILE="$PORTAL_DIR/data/platform-status.json"

[[ -f "$DATA_FILE" ]] || {
  echo "Missing $DATA_FILE"
  echo "Run collect-platform-status.sh first."
  exit 1
}

cd "$REPO"
mkdir -p "$PORTAL_DIR/assets"

cat > "$PORTAL_DIR/assets/styles.css" <<'EOF'
:root{
  --bg:#07111f;
  --panel:#0e1a2c;
  --panel2:#14233a;
  --text:#edf4ff;
  --muted:#9cb0ca;
  --border:#263a59;
  --accent:#55a7ff;
  --pass:#4ade80;
  --warn:#facc15;
  --fail:#fb7185;
}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,system-ui,sans-serif;background:var(--bg);color:var(--text)}
a{color:inherit;text-decoration:none}
.shell{display:grid;grid-template-columns:240px 1fr;min-height:100vh}
.sidebar{background:#091522;border-right:1px solid var(--border);padding:22px 16px}
.brand{font-weight:700;font-size:1.05rem;margin-bottom:4px}
.brand-sub{color:var(--muted);font-size:.8rem;margin-bottom:22px}
.nav a{display:block;padding:10px 12px;border-radius:9px;color:var(--muted);margin-bottom:5px}
.nav a:hover,.nav a.active{background:var(--panel2);color:var(--text)}
.main{padding:28px;max-width:1400px;width:100%}
.header{display:flex;justify-content:space-between;align-items:end;gap:20px;flex-wrap:wrap;margin-bottom:22px}
h1{margin:0;font-size:1.8rem}
.sub{color:var(--muted);font-size:.9rem}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:18px 0}
.card{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:17px}
.label{color:var(--muted);font-size:.8rem}
.value{font-size:1.9rem;font-weight:700;margin-top:6px}
.section{margin-top:24px}
.section h2{font-size:1.1rem;margin-bottom:12px}
.table-wrap{overflow:auto;background:var(--panel);border:1px solid var(--border);border-radius:14px}
table{width:100%;border-collapse:collapse;min-width:720px}
th,td{padding:12px 14px;text-align:left;border-bottom:1px solid var(--border)}
th{background:var(--panel2);color:var(--muted);font-weight:600}
.badge{display:inline-block;padding:4px 9px;border-radius:999px;font-size:.72rem;font-weight:700}
.PASS{color:var(--pass);background:rgba(74,222,128,.12)}
.WARN{color:var(--warn);background:rgba(250,204,21,.12)}
.FAIL{color:var(--fail);background:rgba(251,113,133,.12)}
.good{color:var(--pass)} .warning{color:var(--warn)} .danger{color:var(--fail)}
.kv{display:grid;grid-template-columns:180px 1fr;gap:8px 18px}
.kv div:nth-child(odd){color:var(--muted)}
.note{padding:14px 16px;border-left:4px solid var(--accent);background:var(--panel2);border-radius:8px;color:var(--muted)}
@media(max-width:900px){.shell{grid-template-columns:1fr}.sidebar{border-right:0;border-bottom:1px solid var(--border)}.nav{display:flex;flex-wrap:wrap;gap:5px}.nav a{margin:0}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.main{padding:20px}}
EOF

cat > "$PORTAL_DIR/assets/app.js" <<'EOF'
async function loadData(){
  const res = await fetch('data/platform-status.json', {cache:'no-store'});
  if(!res.ok) throw new Error('Unable to load platform data');
  return res.json();
}
function statusClass(status){ return status; }
function byArea(data, areas){ return data.checks.filter(c => areas.includes(c.area)); }
function renderChecks(el, checks){
  el.innerHTML = checks.map(c => `
    <tr>
      <td>${c.area}</td>
      <td>${c.name}</td>
      <td><span class="badge ${statusClass(c.status)}">${c.status}</span></td>
      <td>${c.detail}</td>
    </tr>`).join('');
}
function metric(id, value){ const el=document.getElementById(id); if(el) el.textContent=value; }
function formatDate(v){ try{return new Date(v).toLocaleString()}catch{return v} }
EOF

NAV='
<nav class="nav">
<a href="index.html">Overview</a>
<a href="infrastructure.html">Infrastructure</a>
<a href="security.html">Security</a>
<a href="performance.html">Performance</a>
<a href="gitops.html">GitOps</a>
<a href="observability.html">Observability</a>
<a href="resilience.html">Resilience</a>
</nav>'

write_page() {
  local file="$1"
  local title="$2"
  local subtitle="$3"
  local body="$4"
  local script="$5"

  cat > "$PORTAL_DIR/$file" <<EOF
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>$title</title>
<link rel="stylesheet" href="assets/styles.css">
</head>
<body>
<div class="shell">
<aside class="sidebar">
<div class="brand">Traditional Strength Platform</div>
<div class="brand-sub">Operations Portal</div>
$NAV
</aside>
<main class="main">
<div class="header">
  <div><h1>$title</h1><div class="sub">$subtitle</div></div>
  <div class="sub" id="generated"></div>
</div>
$body
</main>
</div>
<script src="assets/app.js"></script>
<script>
$script
</script>
</body>
</html>
EOF
}

write_page "index.html" "Platform Overview" "Executive operational summary" '
<section class="grid">
  <div class="card"><div class="label">Platform score</div><div class="value" id="score">-</div></div>
  <div class="card"><div class="label">Passing checks</div><div class="value good" id="pass">-</div></div>
  <div class="card"><div class="label">Warnings</div><div class="value warning" id="warn">-</div></div>
  <div class="card"><div class="label">Failures</div><div class="value danger" id="fail">-</div></div>
</section>
<div class="note">Sanitised portal: no IP addresses, node names, secret values, tenant/client IDs, registry names, Key Vault names or raw manifests.</div>
<section class="section"><h2>All controls</h2><div class="table-wrap"><table><thead><tr><th>Area</th><th>Control</th><th>Status</th><th>Detail</th></tr></thead><tbody id="checks"></tbody></table></div></section>
' '
loadData().then(d=>{
  metric("score", d.score+"%");
  metric("pass", d.summary.pass);
  metric("warn", d.summary.warn);
  metric("fail", d.summary.fail);
  metric("generated", "Generated "+formatDate(d.generated_at));
  renderChecks(document.getElementById("checks"), d.checks);
});
'

write_page "infrastructure.html" "Infrastructure" "AKS, networking and workload state" '
<section class="grid">
<div class="card"><div class="label">Ready nodes</div><div class="value" id="nodes">-</div></div>
<div class="card"><div class="label">Ready replicas</div><div class="value" id="replicas">-</div></div>
<div class="card"><div class="label">Service type</div><div class="value" id="service">-</div></div>
<div class="card"><div class="label">Network policies</div><div class="value" id="policies">-</div></div>
</section>
<section class="section"><h2>Infrastructure checks</h2><div class="table-wrap"><table><thead><tr><th>Area</th><th>Control</th><th>Status</th><th>Detail</th></tr></thead><tbody id="checks"></tbody></table></div></section>
' '
loadData().then(d=>{
 metric("generated","Generated "+formatDate(d.generated_at));
 metric("nodes",d.platform.nodes_ready+"/"+d.platform.nodes_total);
 metric("replicas",d.workload.ready_replicas+"/"+d.workload.desired_replicas);
 metric("service",d.networking.service_type);
 metric("policies",d.networking.network_policy_count);
 renderChecks(document.getElementById("checks"),byArea(d,["Platform","AKS","Workload","Networking","Scheduling"]));
});
'

write_page "security.html" "Security" "Runtime, identity and network controls" '
<section class="grid">
<div class="card"><div class="label">Non-root</div><div class="value" id="nonroot">-</div></div>
<div class="card"><div class="label">Privilege escalation</div><div class="value" id="priv">-</div></div>
<div class="card"><div class="label">Seccomp</div><div class="value" id="seccomp">-</div></div>
<div class="card"><div class="label">External Secret</div><div class="value" id="secret">-</div></div>
</section>
<section class="section"><h2>Security checks</h2><div class="table-wrap"><table><thead><tr><th>Area</th><th>Control</th><th>Status</th><th>Detail</th></tr></thead><tbody id="checks"></tbody></table></div></section>
' '
loadData().then(d=>{
 metric("generated","Generated "+formatDate(d.generated_at));
 metric("nonroot",d.security.run_as_non_root?"PASS":"WARN");
 metric("priv",d.security.privilege_escalation_disabled?"Disabled":"Review");
 metric("seccomp",d.security.seccomp_runtime_default?"RuntimeDefault":"Review");
 metric("secret",d.identity.external_secret_ready?"Ready":"Review");
 renderChecks(document.getElementById("checks"),byArea(d,["Security","Identity","Networking"]));
});
'

write_page "performance.html" "Performance" "Availability and response behaviour" '
<section class="grid">
<div class="card"><div class="label">HTTP status</div><div class="value" id="http">-</div></div>
<div class="card"><div class="label">Health latency</div><div class="value" id="latency">-</div></div>
<div class="card"><div class="label">Container restarts</div><div class="value" id="restarts">-</div></div>
<div class="card"><div class="label">HPA</div><div class="value" id="hpa">-</div></div>
</section>
<section class="section"><h2>Performance checks</h2><div class="table-wrap"><table><thead><tr><th>Area</th><th>Control</th><th>Status</th><th>Detail</th></tr></thead><tbody id="checks"></tbody></table></div></section>
' '
loadData().then(d=>{
 metric("generated","Generated "+formatDate(d.generated_at));
 metric("http",d.availability.http_code);
 metric("latency",d.availability.health_latency_seconds.toFixed(3)+"s");
 metric("restarts",d.workload.container_restarts);
 metric("hpa",d.resilience.hpa_exists?"Configured":"Missing");
 renderChecks(document.getElementById("checks"),byArea(d,["Availability","Performance","Workload","Resilience"]));
});
'

write_page "gitops.html" "GitOps" "Git and Argo CD desired-state status" '
<section class="grid">
<div class="card"><div class="label">Argo sync</div><div class="value" id="sync">-</div></div>
<div class="card"><div class="label">Argo health</div><div class="value" id="health">-</div></div>
<div class="card"><div class="label">Git branch</div><div class="value" id="branch">-</div></div>
<div class="card"><div class="label">Revision</div><div class="value" id="revision">-</div></div>
</section>
<section class="section"><h2>Repository</h2><div class="card"><div class="kv"><div>Working tree</div><div id="clean"></div><div>Last commit</div><div id="commit"></div><div>Commit date</div><div id="commitdate"></div></div></div></section>
<section class="section"><h2>GitOps checks</h2><div class="table-wrap"><table><thead><tr><th>Area</th><th>Control</th><th>Status</th><th>Detail</th></tr></thead><tbody id="checks"></tbody></table></div></section>
' '
loadData().then(d=>{
 metric("generated","Generated "+formatDate(d.generated_at));
 metric("sync",d.gitops.sync_status);
 metric("health",d.gitops.health_status);
 metric("branch",d.git.branch);
 metric("revision",d.git.revision);
 metric("clean",d.git.clean?"Clean":"Local changes");
 metric("commit",d.git.last_commit_message);
 metric("commitdate",formatDate(d.git.last_commit_date));
 renderChecks(document.getElementById("checks"),byArea(d,["GitOps","Repository"]));
});
'

write_page "observability.html" "Observability" "Metrics and telemetry readiness" '
<section class="grid">
<div class="card"><div class="label">Metrics API</div><div class="value" id="metrics">-</div></div>
<div class="card"><div class="label">ServiceMonitor</div><div class="value" id="sm">-</div></div>
<div class="card"><div class="label">Health telemetry</div><div class="value" id="health">-</div></div>
<div class="card"><div class="label">Latency sample</div><div class="value" id="latency">-</div></div>
</section>
<div class="note">Prometheus/Grafana and OpenTelemetry/Application Insights remain the detailed telemetry systems. This portal provides an executive operational summary.</div>
<section class="section"><h2>Observability checks</h2><div class="table-wrap"><table><thead><tr><th>Area</th><th>Control</th><th>Status</th><th>Detail</th></tr></thead><tbody id="checks"></tbody></table></div></section>
' '
loadData().then(d=>{
 metric("generated","Generated "+formatDate(d.generated_at));
 metric("metrics",d.observability.metrics_api_available?"Available":"Review");
 metric("sm",d.observability.service_monitor_present?"Present":"Review");
 metric("health",d.availability.http_code==="200"?"Healthy":"Failed");
 metric("latency",d.availability.health_latency_seconds.toFixed(3)+"s");
 renderChecks(document.getElementById("checks"),byArea(d,["Observability","Availability","Performance"]));
});
'

write_page "resilience.html" "Resilience" "Scaling, disruption and recovery controls" '
<section class="grid">
<div class="card"><div class="label">HPA</div><div class="value" id="hpa">-</div></div>
<div class="card"><div class="label">PDB</div><div class="value" id="pdb">-</div></div>
<div class="card"><div class="label">Startup probe</div><div class="value" id="startup">-</div></div>
<div class="card"><div class="label">Topology spread</div><div class="value" id="spread">-</div></div>
</section>
<section class="section"><h2>Resilience checks</h2><div class="table-wrap"><table><thead><tr><th>Area</th><th>Control</th><th>Status</th><th>Detail</th></tr></thead><tbody id="checks"></tbody></table></div></section>
' '
loadData().then(d=>{
 metric("generated","Generated "+formatDate(d.generated_at));
 metric("hpa",d.resilience.hpa_exists?"Configured":"Missing");
 metric("pdb",d.resilience.pdb_exists?"Configured":"Missing");
 metric("startup",d.resilience.startup_probe?"Configured":"Missing");
 metric("spread",d.resilience.topology_spread?"Configured":"Missing");
 renderChecks(document.getElementById("checks"),byArea(d,["Resilience","Reliability","Scheduling","Workload"]));
});
'

echo "Portal generated under $PORTAL_DIR"

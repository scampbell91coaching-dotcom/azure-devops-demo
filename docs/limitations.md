# Limitations and Future Improvements

## Scope

This is a production-oriented personal platform project, not a complete enterprise landing zone or multi-region business-critical service.

## Current Limitations

### Single Azure Region

A regional outage can make the service unavailable.

Enterprise evolution: secondary region, Azure Front Door or Traffic Manager, replicated state and tested failover.

### Public AKS Control Plane

Unless restricted in Terraform, the AKS API may be publicly reachable behind Azure and Kubernetes authentication controls.

Enterprise evolution: private AKS, private DNS, VPN/ExpressRoute and restricted administration paths.

### Public Ingress Without WAF

NGINX is the public entry point. Azure Front Door, WAF and controlled private origin are not implemented.

### Duplicate Application Exposure

The Flask Service is still `LoadBalancer` while NGINX Ingress also exposes the workload.

Planned remediation:

1. Change Flask Service to `ClusterIP`
2. Verify HTTPS through NGINX
3. Remove the unused public IP/load-balancer rule
4. Retest NetworkPolicies

### Limited Node Capacity

A small node pool controls cost. Replicas may share one node and cluster capacity may be exhausted before scale-out.

Planned: topology spread, pod anti-affinity, Cluster Autoscaler and separate system/user pools.

### No Full Environment Promotion Model

There is no complete development, staging and production promotion path.

Planned: environment values, separate Argo CD Applications, protected GitHub environments and promotion pull requests.

### Ingress Isolation Only

Default-deny ingress exists, but egress is not denied by default.

Planned: default-deny egress, explicit DNS and telemetry allowances, and controlled outbound networking.

### Runtime Hardening Incomplete

Planned:

- `runAsNonRoot`
- fixed non-root UID/GID
- `allowPrivilegeEscalation: false`
- drop all Linux capabilities
- `seccompProfile: RuntimeDefault`
- read-only root filesystem where compatible
- writable `emptyDir` volumes only where required

### Startup and Graceful Termination

Readiness and liveness probes exist. Startup probe, lifecycle hook and validated graceful shutdown are not yet implemented.

### No Image Signature Enforcement

Images use immutable SHA tags and vulnerability scanning, but there is no SBOM, Cosign signature, provenance or admission policy.

### No Formal SLO

Telemetry exists, but formal SLIs, SLOs, error budgets and burn-rate alerts are not yet defined.

### Limited Disaster Recovery

Terraform and Git can reconstruct infrastructure and desired state, but formal RTO/RPO, regional restoration and recovery exercise evidence are not implemented.

### No Service Mesh

This is deliberate for a single application. A mesh would be reconsidered for mutual TLS, advanced traffic policy and multi-service identity.

### Cost-Driven Design

Single region, small nodes, public networking and limited telemetry retention are conscious personal-lab trade-offs.

## Prioritised Backlog

### Priority 1: Runtime and Exposure

1. Change Flask Service to `ClusterIP`
2. Add pod/container security contexts
3. Add startup probe
4. Validate graceful termination
5. Add topology spread

### Priority 2: Network Security

1. Add default-deny egress
2. Allow DNS explicitly
3. Allow required telemetry
4. Test allowed and blocked paths
5. Document trust boundaries

### Priority 3: Supply Chain

1. Generate SBOM
2. Sign image
3. Publish provenance
4. Enforce signature policy
5. Document vulnerability exceptions

### Priority 4: SRE

1. Define SLIs and SLO
2. Calculate error budget
3. Create alerts
4. Conduct failure testing
5. Capture evidence

### Priority 5: Enterprise Evolution

1. Private AKS
2. Private endpoints
3. Dedicated user node pool
4. Azure Front Door and WAF
5. Staging environment
6. Multi-region recovery design

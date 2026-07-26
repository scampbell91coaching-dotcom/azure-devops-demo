# Azure DevOps AKS Platform Demo

A production-style Azure DevOps CI/CD platform that builds, scans and deploys a containerised Flask application to Azure Kubernetes Service using Terraform, Docker, Helm and Azure Container Registry.

The project demonstrates Infrastructure as Code, automated CI/CD, Kubernetes workload management, container security scanning, environment promotion, deployment verification and horizontal autoscaling.

## Architecture

```text
Developer
    |
    v
Azure DevOps Repository
    |
    v
Azure DevOps Pipeline
    |
    +--> Validate application and Helm chart
    |
    +--> Build Docker image
    |
    +--> Scan image with Trivy
    |
    +--> Push image to Azure Container Registry
    |
    +--> Deploy to Demo with Helm
    |
    +--> Verify and smoke test
    |
    +--> Production approval
    |
    +--> Deploy to Production with Helm
    |
    +--> Verify production deployment
              |
              v
     Azure Kubernetes Service
        |              |
        v              v
 Demo namespace   Production namespace
        |
        v
 Horizontal Pod Autoscaler
```

## Technology Stack

- Microsoft Azure
- Azure Kubernetes Service
- Azure Container Registry
- Azure DevOps Pipelines
- Terraform
- Docker
- Kubernetes
- Helm
- Trivy
- Flask
- Bash
- Git

## Key Features

### Infrastructure as Code

- Azure infrastructure managed with Terraform
- AKS cluster provisioning
- Azure Container Registry integration
- Azure networking and resource configuration
- Reproducible infrastructure definitions

### CI/CD Pipeline

The Azure DevOps multi-stage pipeline performs:

1. Application and Helm validation
2. Docker image build
3. Immutable image tagging using the Git commit SHA
4. Push to Azure Container Registry
5. Trivy vulnerability scanning
6. Helm deployment to the Demo namespace
7. Deployment rollout verification
8. Automated smoke testing
9. Production environment approval
10. Helm deployment to Production
11. Production rollout and endpoint verification

### Kubernetes and Helm

- Environment-specific Helm values
- Demo and Production namespaces
- Readiness and liveness probes
- CPU and memory requests
- CPU and memory limits
- Kubernetes Secret templating
- Safe Helm deployments using `--wait` and `--atomic`
- Automated rollback on failed deployments
- Helm release-history management

### Horizontal Pod Autoscaling

The Horizontal Pod Autoscaler uses CPU utilisation to adjust the number of application pods.

| Setting | Value |
|---|---:|
| Minimum replicas | 1 |
| Maximum replicas | 5 |
| Target CPU utilisation | 50% |
| CPU request per pod | 100m |
| Memory request per pod | 128Mi |

Load testing successfully demonstrated automatic scaling from one pod to three pods, followed by scale-down after the load was removed.

### Security

- Trivy container-image vulnerability scanning
- Kubernetes Secrets used for application configuration
- Azure service connections for authenticated deployments
- Immutable container-image tags
- Non-root application container
- Privilege escalation disabled
- Deployment failures automatically rolled back

## Pipeline Flow

```text
Validate
   |
   v
Build and Push
   |
   v
Security Scan
   |
   v
Deploy Demo
   |
   v
Verify and Smoke Test
   |
   v
Production Approval
   |
   v
Deploy Production
   |
   v
Production Verification
```

## Repository Structure

```text
azure-devops-demo/
├── app/
├── flask-app/
│   ├── templates/
│   │   ├── deployment.yaml
│   │   ├── hpa.yaml
│   │   ├── secret.yaml
│   │   └── service.yaml
│   ├── Chart.yaml
│   ├── values.yaml
│   └── values-production.yaml
├── terraform/
├── azure-pipelines.yml
└── README.md
```

## Deployment Reliability

The Helm deployment process includes:

```text
--wait
--atomic
--timeout 5m
--history-max 10
```

This ensures that Helm waits for resources to become healthy, automatically rolls back failed releases, limits deployment duration and retains a controlled release history.

## Troubleshooting Experience

Several realistic deployment issues were diagnosed and resolved during development:

- Kubernetes `CreateContainerConfigError`
- Missing Kubernetes Secret references
- Helm releases stuck in `pending-rollback`
- Helm release-lock recovery
- Azure LoadBalancer external-IP delays
- ClusterIP and LoadBalancer service behaviour
- Pipeline smoke tests for ClusterIP services
- Kubernetes event inspection
- Pod rollout and readiness troubleshooting
- HPA configuration and CPU load testing

## Validation Commands

Check the application resources:

```bash
kubectl get deployments,pods,services,hpa -n demo
```

View live resource usage:

```bash
kubectl top pods -n demo
```

Inspect the autoscaler:

```bash
kubectl describe hpa flask-web-flask-app -n demo
```

Validate the Helm chart:

```bash
helm lint flask-app
```

Render the Kubernetes manifests locally:

```bash
helm template flask-web flask-app --namespace demo
```

## Future Enhancements

- NGINX Ingress Controller
- TLS certificates with cert-manager
- PodDisruptionBudget
- Kubernetes Network Policies
- Prometheus and Grafana
- Loki and Alertmanager
- GitOps with Argo CD
- Azure Key Vault CSI Driver
- Azure Workload Identity
- Azure Policy for Kubernetes

## Screenshots

Planned screenshots:

- Successful Azure DevOps pipeline
- HPA scaling from one to three pods
- AKS workloads
- Azure Container Registry
- Azure resource deployment
- Demo and Production environments

## Author

**Stephen Campbell**

Platform Engineering | Azure | Kubernetes | Terraform | DevOps

# Production-Ready Azure Platform on AKS

A production-style Azure Platform Engineering project demonstrating Infrastructure as Code, Kubernetes, GitOps, CI/CD, secure secret management and observability.

---

# Overview

This project provisions Azure infrastructure using Terraform and deploys a containerised Flask application to Azure Kubernetes Service (AKS).

The deployment uses Helm for Kubernetes packaging, GitHub Actions for continuous integration, and Argo CD for GitOps-based continuous delivery.

The platform also integrates Azure Key Vault for secure secret management, Managed Identity for authentication, Prometheus and Grafana for monitoring, and Azure Application Insights for application telemetry.

---

# Architecture

Detailed architecture documentation can be found here:

**docs/architecture.md**

---

# Technology Stack

## Cloud

- Microsoft Azure
- Azure Kubernetes Service (AKS)
- Azure Container Registry (ACR)
- Azure Key Vault
- Managed Identity
- Azure Application Insights

## Infrastructure

- Terraform

## Kubernetes

- Kubernetes
- Helm
- Argo CD
- NGINX Ingress Controller
- cert-manager
- Secrets Store CSI Driver
- Horizontal Pod Autoscaler

## CI/CD

- GitHub
- GitHub Actions
- Docker
- Trivy

## Observability

- Prometheus
- Grafana
- Azure Application Insights

---

# Features

- Infrastructure as Code using Terraform
- Kubernetes workloads deployed with Helm
- GitOps continuous deployment using Argo CD
- Automated Docker builds
- Azure Container Registry integration
- HTTPS with cert-manager
- Azure Key Vault secret integration
- Managed Identity authentication
- Horizontal Pod Autoscaler
- CPU and memory resource requests
- Readiness probes
- Liveness probes
- Prometheus monitoring
- Grafana dashboards
- Application Insights telemetry

---

# Deployment Workflow

```text
Developer

↓

GitHub Repository

↓

GitHub Actions

↓

Docker Build

↓

Trivy Security Scan

↓

Azure Container Registry

↓

Argo CD

↓

Helm Chart

↓

Azure Kubernetes Service

↓

Flask Application
```

---

# GitOps Workflow

The Kubernetes application is managed entirely through Git.

When changes are pushed:

1. GitHub Actions builds a new container image.
2. The image is pushed to Azure Container Registry.
3. The Helm chart references the required image.
4. Argo CD detects changes in Git.
5. Kubernetes automatically reconciles to the desired state.
6. Configuration drift is automatically repaired.

---

# Security

Security features include:

- Azure Managed Identity
- Azure Key Vault
- Secrets Store CSI Driver
- HTTPS via cert-manager
- Trivy container image scanning
- Kubernetes resource limits
- Environment-specific Helm values

---

# Monitoring

Platform observability includes:

- Prometheus
- Grafana
- Azure Application Insights

These provide infrastructure, Kubernetes and application-level monitoring.

---

# Repository Structure

```text
.
├── terraform/
│
├── flask-app/
│   ├── templates/
│   ├── values.yaml
│   └── values-production.yaml
│
├── kubernetes/
│   ├── argocd/
│   ├── ingress/
│   ├── keyvault/
│   └── monitoring/
│
├── docs/
│   ├── architecture.md
│   └── images/
│
├── .github/
│   └── workflows/
│
└── README.md
```

---

# Validation

Validate the Helm chart

```bash
helm lint flask-app
```

Validate production values

```bash
helm lint flask-app \
  -f flask-app/values-production.yaml
```

Render production manifests

```bash
helm template flask-web-prod flask-app \
  -f flask-app/values-production.yaml
```

---

# Kubernetes Validation

Check workloads

```bash
kubectl get pods,svc,ingress,hpa \
  -n production
```

Check Key Vault integration

```bash
kubectl get secretproviderclass \
  -n production
```

Check deployment

```bash
kubectl get deployment flask-web \
  -n production
```

---

# Argo CD Validation

Check GitOps status

```bash
kubectl get applications \
  -n argocd
```

Expected output

```text
SYNC STATUS     HEALTH STATUS

Synced          Healthy
```

---

# Lessons Learned

During this project I gained practical experience with:

- Terraform
- Azure networking
- AKS
- Helm templating
- GitHub Actions
- Argo CD
- GitOps
- Azure Key Vault
- Managed Identity
- Kubernetes troubleshooting
- Horizontal Pod Autoscaling
- Prometheus
- Grafana
- Application Insights

---

# Future Improvements

Potential future enhancements include:

- Azure Workload Identity
- Azure Policy
- Kubernetes Network Policies
- Pod Disruption Budgets
- Alertmanager
- Argo CD ApplicationSets
- Progressive Delivery
- Kubeconform validation
- Helm unit testing

---

# Project Status

✅ Terraform infrastructure

✅ Azure Kubernetes Service

✅ Azure Container Registry

✅ GitHub Actions CI

✅ Helm deployment

✅ Argo CD GitOps

✅ Azure Key Vault

✅ Managed Identity

✅ HTTPS ingress

✅ Prometheus

✅ Grafana

✅ Application Insights

✅ Production-ready Kubernetes deployment

---

# Author

**Stephen Campbell**

Senior Observability & Platform Engineer

Azure • Kubernetes • Terraform • DevOps • Platform Engineering

---

## Platform Screenshots

### GitHub Repository

![GitHub repository overview](docs/images/github-repository-overview.png)

### CI/CD Pipeline

![GitHub Actions pipeline success](docs/images/github-actions-pipeline-success.png)

### GitOps Deployment

![Argo CD application healthy and synced](docs/images/argocd-application-healthy-synced.png)

### Azure Infrastructure

![Azure resource group overview](docs/images/azure-resource-group-overview.png)

### Application Insights

![Application Insights performance overview](docs/images/application-insights-overview.png)

### Grafana Monitoring

#### Grafana Home

![Grafana home](docs/images/grafana-home.png)

#### Kubernetes Cluster Dashboard

![Grafana Kubernetes cluster dashboard](docs/images/grafana-kubernetes-cluster-dashboard.png)

#### Kubernetes Namespace Dashboard

![Grafana Kubernetes namespace dashboard](docs/images/grafana-kubernetes-namespace-dashboard.png)

#### Kubernetes Pod Dashboard

![Grafana Kubernetes pod dashboard](docs/images/grafana-kubernetes-pod-dashboard.png)

### Prometheus

#### Target Health

![Prometheus targets](docs/images/prometheus-targets.png)

#### Query Results

![Prometheus query results](docs/images/prometheus-query-results.png)

### Kubernetes Resources

![Kubernetes production resources](docs/images/kubectl-production-resources.png)

### HTTPS Application

![Application running over HTTPS](docs/images/application-https.png)


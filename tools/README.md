# Platform Toolkit v1.0

Developer-experience toolkit for the Traditional Strength Azure platform.

## Included

- `00-doctor.sh` — checks the local toolchain, Azure, AKS and portal
- `01-verify-platform.sh` — runs quality and security gates
- `02-create-feature.sh` — creates a complete portal feature skeleton
- `03-create-api.sh` — creates a versioned API blueprint
- `04-create-service.sh` — creates a service class
- `05-create-repository.sh` — creates a repository class
- `06-create-page.sh` — creates a portal page and JavaScript module
- `07-create-chart.sh` — creates a Chart.js module
- `08-create-db-table.sh` — creates SQLAlchemy model/repository/test scaffolding
- `09-release.sh` — validates and creates a semantic-version Git tag
- `10-new-dashboard.sh` — creates a dashboard page with cards and a chart

## Install

```bash
mkdir -p ~/azure-devops-demo/tools
cp *.sh ~/azure-devops-demo/tools/
cp README.md ~/azure-devops-demo/tools/
chmod +x ~/azure-devops-demo/tools/*.sh
```

## First checks

```bash
~/azure-devops-demo/tools/00-doctor.sh
~/azure-devops-demo/tools/01-verify-platform.sh --fast
```

## Generate a feature

```bash
~/azure-devops-demo/tools/02-create-feature.sh history
```

Generators deliberately avoid silently modifying application registration and navigation. They print the small manual wiring steps required after generation, keeping architectural decisions visible and reviewable.

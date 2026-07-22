# Azure Observability Platform with Terraform

## Overview

This project provisions a production-style Azure infrastructure using Terraform.

It demonstrates Infrastructure as Code, modular Terraform design, remote state management, Azure monitoring, OpenTelemetry, and containerised workloads.

## Architecture

- Azure Resource Group
- Virtual Network
- Network Security Groups
- Ubuntu Linux Virtual Machine
- Dockerised Flask application
- Azure Monitor Agent
- Log Analytics Workspace
- Application Insights
- Azure Managed Grafana
- Azure Monitor Alerts

## Terraform Structure

modules/
- resource-group
- network
- compute
- monitoring

environments/
- dev

## Features

- Modular Terraform architecture
- Remote state stored in Azure Storage
- Azure AD authenticated backend
- State locking
- Environment-specific configuration
- Production-style project structure

## Technologies

- Terraform
- Azure
- Docker
- Flask
- OpenTelemetry
- Azure Monitor
- Log Analytics
- Application Insights
- Grafana

## Future Improvements

- GitHub Actions CI/CD
- AKS deployment
- Helm
- Argo CD
- Multiple environments (dev / prod)

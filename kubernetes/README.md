# Kubernetes Deployment

This directory contains the Kubernetes manifests used to deploy the Flask application to Azure Kubernetes Service (AKS).

Contents:

- namespace.yaml
- deployment.yaml
- service.yaml

Future additions:

- ingress.yaml
- configmap.yaml
- secret.yaml
- hpa.yaml
- networkpolicy.yaml

Deployment:

kubectl apply -f namespace.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

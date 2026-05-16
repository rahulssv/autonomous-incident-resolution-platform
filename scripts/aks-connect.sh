#!/usr/bin/env bash
set -euo pipefail

SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-568d5cd8-cd2c-4170-ae3e-0b93b2cc39aa}"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-Semicolon-AIRP-rg}"
CLUSTER_NAME="${AZURE_AKS_CLUSTER_NAME:-AIRP-cluster-high-per}"

az login
az account set --subscription "${SUBSCRIPTION_ID}"
az aks install-cli
az aks get-credentials \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${CLUSTER_NAME}" \
  --overwrite-existing

kubectl config current-context
kubectl get nodes


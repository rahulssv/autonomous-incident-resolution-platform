# AIRP Backend Deployment Guide

## 1. Connect to AKS

```bash
./scripts/aks-connect.sh
```

The script uses these defaults:

```text
AZURE_SUBSCRIPTION_ID=568d5cd8-cd2c-4170-ae3e-0b93b2cc39aa
AZURE_RESOURCE_GROUP=Semicolon-AIRP-rg
AZURE_AKS_CLUSTER_NAME=AIRP-cluster-high-per
```

Override them with environment variables when needed.

## 2. Build and Push Docker Image

```bash
docker build -t docker.io/<your-org>/airp-backend:0.1.0 .
docker push docker.io/<your-org>/airp-backend:0.1.0
```

Update `deploy/helm/airp/values.yaml`:

```yaml
image:
  repository: docker.io/<your-org>/airp-backend
  tag: "0.1.0"
```

## 3. Configure Microsoft Entra ID

Create or reuse an Entra ID app registration for the AIRP API.

Required runtime values:

```text
AIRP_ENTRA_TENANT_ID=<tenant-id>
AIRP_ENTRA_CLIENT_ID=<api-application-client-id>
```

Tokens must be issued by the configured tenant and have `aud` equal to `AIRP_ENTRA_CLIENT_ID`.

## 4. Configure Azure Event Hubs Kafka Endpoint

Create an Event Hubs namespace and event hub topics that match the AIRP Kafka topic plan.

Runtime values:

```text
AIRP_KAFKA_BOOTSTRAP_SERVERS=<namespace>.servicebus.windows.net:9093
AIRP_KAFKA_SECURITY_PROTOCOL=SASL_SSL
AIRP_KAFKA_SASL_MECHANISM=PLAIN
AIRP_KAFKA_USERNAME=$ConnectionString
AIRP_KAFKA_PASSWORD=<event-hubs-connection-string>
```

Store `AIRP_KAFKA_PASSWORD` in Kubernetes Secret only.

## 5. Configure GenAI Hub

Runtime values:

```text
AIRP_GATEWAY_BASE_URL=https://hub-proxy-service.thankfulfield-16b4d5d6.eastus.azurecontainerapps.io
AIRP_GATEWAY_API_KEY=<secret>
```

Store `AIRP_GATEWAY_API_KEY` in Kubernetes Secret only.

## 6. Database and Redis

For production, use managed or cluster-hosted PostgreSQL with pgvector enabled and a production Redis instance.

Apply migrations:

```bash
AIRP_DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>:5432/<db> alembic upgrade head
```

## 7. Helm Deploy

Create a production values file, for example `deploy/helm/airp/prod-values.yaml`:

```yaml
image:
  repository: docker.io/<your-org>/airp-backend
  tag: "0.1.0"

env:
  AIRP_ENVIRONMENT: production
  AIRP_DATABASE_URL: postgresql+asyncpg://<user>:<password>@<host>:5432/<db>
  AIRP_REDIS_URL: redis://<host>:6379/0
  AIRP_ENTRA_TENANT_ID: <tenant-id>
  AIRP_ENTRA_CLIENT_ID: <client-id>
  AIRP_KAFKA_BOOTSTRAP_SERVERS: <namespace>.servicebus.windows.net:9093

secretEnv:
  AIRP_GATEWAY_API_KEY: <secret>
  AIRP_KAFKA_PASSWORD: <event-hubs-connection-string>
```

Install:

```bash
helm upgrade --install airp deploy/helm/airp \
  --namespace airp \
  --create-namespace \
  -f deploy/helm/airp/prod-values.yaml
```

Check rollout:

```bash
kubectl -n airp rollout status deploy/airp-airp
kubectl -n airp get pods
kubectl -n airp port-forward svc/airp-airp 8080:80
curl http://localhost:8080/api/health
```

## 8. Security Checklist

- Keep Microsoft Entra ID auth enabled.
- Store GenAI Hub, Event Hubs, GitHub, Slack, and database secrets in Kubernetes Secrets or external secret manager.
- Do not expose `/docs` in production; the app disables docs when `AIRP_ENVIRONMENT=production`.
- Use read-only Kubernetes MCP permissions for MVP.
- Use least-privilege GitHub MCP permissions scoped to AIRP-client repositories.
- Require human approval before repository write actions.


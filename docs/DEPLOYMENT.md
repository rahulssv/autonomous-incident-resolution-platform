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
AIRP_KAFKA_ALERTS_RAW_TOPIC=airp.alerts.raw
AIRP_KAFKA_DEADLETTER_TOPIC=airp.deadletter
AIRP_KAFKA_ALERT_CONSUMER_GROUP=airp-alert-consumer
```

Store `AIRP_KAFKA_PASSWORD` in Kubernetes Secret only.

## 5. Configure GenAI Hub

Runtime values:

```text
AIRP_GATEWAY_BASE_URL=https://hub-proxy-service.thankfulfield-16b4d5d6.eastus.azurecontainerapps.io
AIRP_GATEWAY_API_KEY=<secret>
```

Store `AIRP_GATEWAY_API_KEY` in Kubernetes Secret only.

## 6. Configure Read-Only Evidence Integrations

AIRP can collect RCA evidence from Kubernetes MCP, GitHub MCP, and public DockerHub
metadata when read-only evidence is enabled.

Runtime values:

```text
AIRP_AGENT_READ_ONLY_EVIDENCE_ENABLED=true
AIRP_KUBERNETES_MCP_TRANSPORT=mcp
AIRP_KUBERNETES_MCP_URL=https://<kubernetes-mcp-host>
AIRP_KUBERNETES_MCP_NAMESPACE_ALLOWLIST=shopfast,payments,catalog
AIRP_KUBERNETES_MCP_READ_TIMEOUT_SECONDS=20
AIRP_GITHUB_MCP_TRANSPORT=mcp
AIRP_GITHUB_MCP_URL=https://<github-mcp-host>
AIRP_GITHUB_MCP_REPOSITORY_ALLOWLIST=AIRP-client/*
AIRP_GITHUB_MCP_READ_TIMEOUT_SECONDS=20
AIRP_DOCKERHUB_BASE_URL=https://hub.docker.com/v2
AIRP_DOCKERHUB_READ_TIMEOUT_SECONDS=20
AIRP_MCP_READ_RETRY_ATTEMPTS=2
AIRP_READINESS_ACTIVE_CHECKS_ENABLED=false
AIRP_READINESS_PROBE_TIMEOUT_SECONDS=2
```

Namespace allowlisting should include only AKS namespaces that run AIRP-client
services. Repository allowlisting should remain scoped to `AIRP-client/*` unless a
specific service repository needs a narrower allowlist such as
`AIRP-client/checkout-api`.

The current product only performs read-only evidence collection. GitHub issue
creation, Slack sends, remediation PR creation, and documentation publishing remain
disabled unless their explicit policy flags are enabled in a later governed rollout.

Check the configuration surface after deployment:

```bash
curl http://localhost:8080/api/readiness
curl http://localhost:8080/api/readiness?active=true
```

The current read-only MCP HTTP bridge contract is intentionally small:

```http
POST <AIRP_*_MCP_URL>/tools/call
Content-Type: application/json
Accept: application/json
```

```json
{
  "tool": "kubernetes.list_pods",
  "arguments": {
    "namespace": "shopfast"
  }
}
```

Responses may be direct JSON, `{"result": ...}`, `{"data": ...}`, or MCP-style
`{"content": [{"type": "json", "json": ...}]}`. AIRP currently uses only
read-only tool names under the `kubernetes.*` and `github.*` prefixes.

Keep `AIRP_READINESS_ACTIVE_CHECKS_ENABLED=false` for high-frequency Kubernetes
readiness probes unless the target dependencies can tolerate periodic active checks.
Use `?active=true` for operator diagnostics or enable the flag in environments where
active readiness should gate traffic.

## 7. Database and Redis

For production, use managed or cluster-hosted PostgreSQL with pgvector enabled and a production Redis instance.

Apply migrations:

```bash
AIRP_DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>:5432/<db> alembic upgrade head
```

## 8. Configure Temporal

Runtime values:

```text
AIRP_TEMPORAL_ADDRESS=<temporal-host>:7233
AIRP_TEMPORAL_NAMESPACE=default
AIRP_TEMPORAL_TASK_QUEUE=airp-incident-workflows
AIRP_TEMPORAL_START_WORKFLOWS=true
```

Run the Temporal worker locally:

```bash
./scripts/run-temporal-worker.sh
```

In production, deploy it as a separate worker Deployment using:

```bash
python -m airp.workers.temporal_worker
```

## 9. Helm Deploy

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
  AIRP_TEMPORAL_ADDRESS: <temporal-host>:7233
  AIRP_AGENT_READ_ONLY_EVIDENCE_ENABLED: "true"
  AIRP_KUBERNETES_MCP_TRANSPORT: mcp
  AIRP_KUBERNETES_MCP_URL: https://<kubernetes-mcp-host>
  AIRP_KUBERNETES_MCP_NAMESPACE_ALLOWLIST: shopfast,payments,catalog
  AIRP_GITHUB_MCP_TRANSPORT: mcp
  AIRP_GITHUB_MCP_URL: https://<github-mcp-host>
  AIRP_GITHUB_MCP_REPOSITORY_ALLOWLIST: AIRP-client/*

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
curl http://localhost:8080/api/readiness
curl http://localhost:8080/api/readiness?active=true
```

Run the alert consumer in the same environment:

```bash
./scripts/run-alert-consumer.sh
```

Publish a sample Alertmanager-shaped event into the raw alert topic:

```bash
./scripts/publish-sample-alert.py
```

Expected demo flow:

```text
sample Alertmanager payload -> Event Hubs Kafka topic -> alert consumer -> incidents row -> incident.created and alert.validated events
```

In production this should be packaged as a separate worker Deployment that uses the same image with command:

```bash
python -m airp.workers.alert_consumer
```

The Helm chart includes separate Deployments for the API, alert consumer, and Temporal worker. Disable workers in `values.yaml` only when running them outside the chart.

## 10. Security Checklist

- Keep Microsoft Entra ID auth enabled.
- Store GenAI Hub, Event Hubs, GitHub, Slack, and database secrets in Kubernetes Secrets or external secret manager.
- Do not expose `/docs` in production; the app disables docs when `AIRP_ENVIRONMENT=production`.
- Use read-only Kubernetes MCP permissions and an explicit AKS namespace allowlist for MVP.
- Use least-privilege GitHub MCP permissions scoped to AIRP-client repositories and keep `AIRP_GITHUB_MCP_REPOSITORY_ALLOWLIST` scoped to `AIRP-client/*` or narrower.
- Require human approval before repository write actions.

## 11. Dependency Outage Runbook

Use `/api/readiness?active=true` to identify failing dependencies. The response does
not include secrets and reports each dependency as `ready`, `disabled`,
`misconfigured`, or `unavailable`.

Kubernetes MCP outage:

- Confirm `AIRP_KUBERNETES_MCP_URL`, namespace allowlist, and AKS read-only identity.
- Check the Kubernetes MCP server logs and AKS API connectivity.
- AIRP should continue incident processing with partial or unavailable Kubernetes
  evidence events in the incident timeline.

GitHub MCP outage:

- Confirm `AIRP_GITHUB_MCP_URL` and `AIRP_GITHUB_MCP_REPOSITORY_ALLOWLIST`.
- Check GitHub MCP server logs and AIRP-client credential scope.
- Repository write actions remain disabled unless policy flags are explicitly enabled.

DockerHub outage:

- Confirm outbound access to `AIRP_DOCKERHUB_BASE_URL`.
- RCA can still use Kubernetes and GitHub evidence, but image digest/source metadata
  may be partial.

GenAI Hub outage:

- Confirm `AIRP_GATEWAY_BASE_URL` and secret-backed `AIRP_GATEWAY_API_KEY`.
- Low-evidence or model-failure RCA paths should escalate instead of fabricating a
  conclusion.

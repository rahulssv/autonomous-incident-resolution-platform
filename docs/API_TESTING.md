# AIRP Backend API Local Testing Guide

This guide brings up the AIRP Backend API locally and walks through public smoke
checks plus an authenticated API flow.

## Prerequisites

- Python 3.12 or newer
- Docker with Docker Compose v2
- `curl`
- `jq` for the copy-paste test flow below
- Azure CLI only if you want to test protected endpoints with a real Microsoft
  Entra token

## 1. Install local dependencies

Run from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Create local configuration:

```bash
cp .env.example .env
```

For local database/API testing, keep these values:

```bash
AIRP_DATABASE_URL=postgresql+asyncpg://airp:airp@localhost:5432/airp
AIRP_REDIS_URL=redis://localhost:6379/0
AIRP_TEMPORAL_ADDRESS=localhost:7233
AIRP_TEMPORAL_NAMESPACE=default
AIRP_TEMPORAL_TASK_QUEUE=airp-incident-workflows
```

For authenticated endpoint testing, also fill:

```bash
AIRP_ENTRA_TENANT_ID=<tenant-id>
AIRP_ENTRA_CLIENT_ID=<api-app-client-id>
```

`AIRP_AUTH_ENABLED=false` is not a local bypass in this product. Protected routes
will return `503` if auth is disabled, so use a valid Entra bearer token for CRUD
tests.

If you are not testing GenAI Hub, leave `AIRP_GATEWAY_BASE_URL` and
`AIRP_GATEWAY_API_KEY` blank in `.env`. Setting only the base URL without an API key
is valid for app startup, but `/api/readiness` reports GenAI Hub as misconfigured
and the overall readiness status as `degraded`.

## 2. Start backing services

```bash
docker compose up -d postgres redis temporal
docker compose ps
```

Wait until `postgres` and `redis` are healthy. Then apply database migrations:

```bash
alembic upgrade head
```

Start the API:

```bash
./scripts/run-api.sh
```

The API listens on `http://localhost:8080`.

## 3. Public smoke checks

Use a second terminal:

```bash
export BASE_URL=http://localhost:8080

curl -sS "$BASE_URL/" | jq .
curl -sS "$BASE_URL/api/health" | jq .
curl -sS "$BASE_URL/api/readiness" | jq .
curl -sS "$BASE_URL/api/readiness?active=true" | jq .
```

Expected:

- `/` returns the service name and `status: ok`.
- `/api/health` returns `status: healthy`.
- `/api/readiness` returns dependency configuration status.
- `/docs` opens the FastAPI Swagger UI in development.

Protected endpoints without a token should return `401`:

```bash
curl -i "$BASE_URL/api/incidents"
```

## 4. Get an Entra bearer token

Configure the AIRP API app registration with these app roles:

```text
AIRP.Admin
AIRP.SRE
AIRP.Viewer
AIRP.Approver
```

For the full test flow below, use a caller with `AIRP.Admin`. Admin can call
catalog, incident, approval, and read endpoints. A narrower incident-only flow can
use `AIRP.SRE`; approval decisions need `AIRP.Approver` or `AIRP.Admin`.

Get a token for the AIRP API resource. In many Entra setups, the Application ID URI
is `api://<api-app-client-id>`:

```bash
az login --tenant <tenant-id>

export AIRP_TOKEN="$(
  az account get-access-token \
    --tenant <tenant-id> \
    --resource api://<api-app-client-id> \
    --query accessToken \
    -o tsv
)"
```

If your app registration uses a different Application ID URI, use that value in
`--resource`. The access token must have:

- `aud` equal to `AIRP_ENTRA_CLIENT_ID`
- `tid` equal to `AIRP_ENTRA_TENANT_ID`
- `roles` containing one of the AIRP roles required by the route

## 5. Authenticated happy-path API test

Set common variables:

```bash
export BASE_URL=http://localhost:8080
export RUN_ID="$(date +%Y%m%d%H%M%S)"
```

Create a service catalog entry. Requires `AIRP.Admin`:

```bash
SERVICE_RESPONSE=$(
  curl -sS -X POST "$BASE_URL/api/services" \
    -H "Authorization: Bearer ${AIRP_TOKEN}" \
    -H "Content-Type: application/json" \
    -d @- <<JSON
{
  "name": "checkout-api-${RUN_ID}",
  "owner": "sre-platform",
  "environment": "prod",
  "namespace": "shopfast",
  "deployment": "checkout-api",
  "repository_url": "https://github.com/AIRP-client/checkout-api",
  "docker_image": "docker.io/airp-client/checkout-api:local",
  "slack_channel": "#airp-dev",
  "metadata": {
    "test_run": "${RUN_ID}"
  }
}
JSON
)

echo "$SERVICE_RESPONSE" | jq .
export SERVICE_ID="$(echo "$SERVICE_RESPONSE" | jq -r .id)"
```

Create an incident. Requires `AIRP.SRE` or `AIRP.Admin`:

```bash
INCIDENT_RESPONSE=$(
  curl -sS -X POST "$BASE_URL/api/incidents" \
    -H "Authorization: Bearer ${AIRP_TOKEN}" \
    -H "Content-Type: application/json" \
    -d @- <<JSON
{
  "title": "Local checkout latency spike ${RUN_ID}",
  "description": "Manual API smoke test incident.",
  "idempotency_key": "manual-api-test-${RUN_ID}",
  "service_id": "${SERVICE_ID}",
  "severity": "critical",
  "environment": "prod",
  "owner": "sre-platform",
  "correlation_id": "corr-${RUN_ID}",
  "namespace": "shopfast",
  "pod_name": "checkout-api-7d9c-local",
  "image_tag": "docker.io/airp-client/checkout-api:local",
  "metadata": {
    "source": "manual-curl"
  }
}
JSON
)

echo "$INCIDENT_RESPONSE" | jq .
export INCIDENT_ID="$(echo "$INCIDENT_RESPONSE" | jq -r .id)"
```

Read the incident and timeline:

```bash
curl -sS "$BASE_URL/api/incidents/$INCIDENT_ID" \
  -H "Authorization: Bearer ${AIRP_TOKEN}" | jq .

curl -sS "$BASE_URL/api/incidents/$INCIDENT_ID/timeline" \
  -H "Authorization: Bearer ${AIRP_TOKEN}" | jq .
```

Add evidence:

```bash
curl -sS -X POST "$BASE_URL/api/incidents/$INCIDENT_ID/evidence" \
  -H "Authorization: Bearer ${AIRP_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "evidence_type": "metric",
    "source": "manual-test",
    "summary": "p95 latency exceeded the local smoke threshold.",
    "data": {
      "p95_ms": 1250,
      "window": "5m"
    }
  }' | jq .
```

Create a remediation plan:

```bash
curl -sS -X POST "$BASE_URL/api/incidents/$INCIDENT_ID/remediation-plans" \
  -H "Authorization: Bearer ${AIRP_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "plan_summary": "Roll back the checkout API image and monitor p95 latency.",
    "risk_level": "medium",
    "test_plan": "Run smoke checks and verify latency recovers.",
    "rollback_plan": "Reapply the previous deployment revision.",
    "approval_required": true,
    "metadata": {
      "created_by": "manual-test"
    }
  }' | jq .
```

Request and approve an approval. The request requires `AIRP.SRE` or `AIRP.Admin`;
the decision requires `AIRP.Approver` or `AIRP.Admin`:

```bash
APPROVAL_RESPONSE=$(
  curl -sS -X POST "$BASE_URL/api/incidents/$INCIDENT_ID/approvals" \
    -H "Authorization: Bearer ${AIRP_TOKEN}" \
    -H "Content-Type: application/json" \
    -d @- <<JSON
{
  "requested_action": "rollback checkout-api deployment",
  "requested_by": "manual-tester",
  "payload_hash": "manual-test-${RUN_ID}",
  "metadata": {
    "test_run": "${RUN_ID}"
  }
}
JSON
)

echo "$APPROVAL_RESPONSE" | jq .
export APPROVAL_ID="$(echo "$APPROVAL_RESPONSE" | jq -r .id)"

curl -sS -X POST "$BASE_URL/api/approvals/$APPROVAL_ID/decision" \
  -H "Authorization: Bearer ${AIRP_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "approved",
    "approver": "manual-approver",
    "metadata": {
      "reason": "local smoke test"
    }
  }' | jq .
```

Close the incident:

```bash
curl -sS -X POST "$BASE_URL/api/incidents/$INCIDENT_ID/signals" \
  -H "Authorization: Bearer ${AIRP_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "closed",
    "reason": "manual API test completed",
    "payload": {
      "verified_by": "curl"
    }
  }' | jq .
```

Verify list/search/audit endpoints:

```bash
curl -sS "$BASE_URL/api/incidents?limit=10" \
  -H "Authorization: Bearer ${AIRP_TOKEN}" | jq .

curl -sS "$BASE_URL/api/search/incidents?q=checkout" \
  -H "Authorization: Bearer ${AIRP_TOKEN}" | jq .

curl -sS "$BASE_URL/api/incidents/$INCIDENT_ID/audit/export" \
  -H "Authorization: Bearer ${AIRP_TOKEN}" | jq .

curl -sS "$BASE_URL/api/incidents/$INCIDENT_ID/workflow/state" \
  -H "Authorization: Bearer ${AIRP_TOKEN}" | jq .
```

If you did not start workflows for this incident, `workflow/state` should return
`has_workflow: false`.

## 6. Run automated verification

```bash
./scripts/verify.sh
```

This runs compile checks, Ruff, and the pytest suite.

## 7. Optional Docker-only API flow

The local virtualenv flow above is best while developing. To run the API container:

```bash
docker compose up -d postgres redis temporal
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose up -d api
docker compose logs -f api
```

Then use the same smoke checks against `http://localhost:8080`.

## 8. Optional workers

Temporal worker:

```bash
./scripts/run-temporal-worker.sh
```

Alert consumer:

```bash
./scripts/run-alert-consumer.sh
```

The alert consumer needs Event Hubs Kafka settings in `.env`:

```bash
AIRP_KAFKA_BOOTSTRAP_SERVERS=<event-hubs-namespace>.servicebus.windows.net:9093
AIRP_KAFKA_USERNAME=$ConnectionString
AIRP_KAFKA_PASSWORD=<event-hubs-connection-string>
AIRP_KAFKA_ALERTS_RAW_TOPIC=airp.alerts.raw
AIRP_KAFKA_DEADLETTER_TOPIC=airp.deadletter
```

Publish a sample alert after the consumer is running:

```bash
./scripts/publish-sample-alert.py
```

To run the live Docker Compose E2E path with a unique Kafka/Event Hubs alert,
database migrations, temporary Temporal and alert-consumer workers, active
dependency reachability checks, workflow polling, and cleanup:

```bash
./scripts/run-e2e-kafka.sh
```

Useful options:

```bash
AIRP_E2E_TIMEOUT_SECONDS=900 ./scripts/run-e2e-kafka.sh
AIRP_E2E_REQUIRE_EVIDENCE=true ./scripts/run-e2e-kafka.sh
AIRP_E2E_MIGRATE=0 AIRP_E2E_BUILD=0 ./scripts/run-e2e-kafka.sh
AIRP_E2E_BUILD=0 ./scripts/run-e2e-kafka.sh --leave-workflow-open
```

The E2E wrapper starts the alert consumer with a unique consumer group and
`AIRP_KAFKA_AUTO_OFFSET_RESET=latest` so it consumes only alerts published during
that run instead of replaying old messages from a shared live topic.

## Troubleshooting

- `401 Missing bearer token`: send `Authorization: Bearer <token>`.
- `403 Insufficient role`: the token is valid but does not include the AIRP role
  required by the route.
- `503 Microsoft Entra ID authentication is not configured`: set
  `AIRP_ENTRA_TENANT_ID` and `AIRP_ENTRA_CLIENT_ID`.
- `503 Microsoft Entra ID discovery failed`: check tenant ID, outbound network, and
  Entra discovery availability.
- `500 database_error` or `relation does not exist`: run `alembic upgrade head`.
- `address already in use`: set another API port, for example `PORT=8081 ./scripts/run-api.sh`.
- `/api/readiness` is `degraded`: inspect the dependency block. For local tests,
  a missing GenAI Hub key or Event Hubs configuration can be acceptable if you are
  only testing core CRUD endpoints.

To stop local services:

```bash
docker compose down
```

To reset the local database and remove all local Docker data for this stack:

```bash
docker compose down -v
```

# AIRP Backend API

Backend/API service for the Autonomous Incident Resolution Platform.

AIRP detects production incidents, records evidence, correlates AKS pod images back to DockerHub images and AIRP-client repositories, stores RCA context, and exposes APIs for incident management, approvals, remediation plans, and audit timelines.

This repository is backend/API only. A future SRE command center or external dashboard should consume these REST APIs.

## Stack

- Python 3.12
- FastAPI
- SQLAlchemy 2 async
- PostgreSQL + pgvector
- Redis
- Temporal Python SDK
- Azure Event Hubs Kafka-compatible endpoint
- Microsoft Entra ID bearer-token authentication
- GenAI Hub OpenAI-compatible gateway
- Docker and Helm for AKS deployment

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d postgres redis temporal
alembic upgrade head
./scripts/run-api.sh
```

Open:

```text
http://localhost:8080/docs
http://localhost:8080/api/health
```

Protected APIs require a Microsoft Entra ID bearer token. Health remains public for probes.

## Key Configuration

Use environment variables. Do not commit secrets.

```bash
AIRP_DATABASE_URL=postgresql+asyncpg://airp:airp@localhost:5432/airp
AIRP_REDIS_URL=redis://localhost:6379/0

AIRP_ENTRA_TENANT_ID=<tenant-id>
AIRP_ENTRA_CLIENT_ID=<api-app-client-id>

AIRP_GATEWAY_BASE_URL=https://hub-proxy-service.thankfulfield-16b4d5d6.eastus.azurecontainerapps.io
AIRP_GATEWAY_API_KEY=<secret>

AIRP_KAFKA_BOOTSTRAP_SERVERS=<event-hubs-namespace>.servicebus.windows.net:9093
AIRP_KAFKA_USERNAME=$ConnectionString
AIRP_KAFKA_PASSWORD=<event-hubs-connection-string>
AIRP_KAFKA_ALERTS_RAW_TOPIC=airp.alerts.raw
AIRP_KAFKA_DEADLETTER_TOPIC=airp.deadletter

AIRP_TEMPORAL_ADDRESS=localhost:7233
AIRP_TEMPORAL_NAMESPACE=default
AIRP_TEMPORAL_TASK_QUEUE=airp-incident-workflows
```

## API Surface

- `GET /api/health`
- `POST /api/incidents`
- `GET /api/incidents`
- `GET /api/incidents/{incident_id}`
- `GET /api/incidents/{incident_id}/timeline`
- `GET /api/incidents/{incident_id}/audit`
- `POST /api/incidents/{incident_id}/signals`
- `POST /api/incidents/{incident_id}/workflow/signals`
- `POST /api/incidents/{incident_id}/evidence`
- `POST /api/incidents/{incident_id}/remediation-plans`
- `POST /api/incidents/{incident_id}/approvals`
- `POST /api/approvals/{approval_id}/decision`
- `POST /api/services`
- `GET /api/services`
- `POST /api/repositories`
- `GET /api/repositories`
- `POST /api/workloads`
- `GET /api/workloads`
- `GET /api/search/incidents`

## Verification

```bash
./scripts/verify.sh
```

For a step-by-step local API runbook with curl examples, see
[docs/API_TESTING.md](docs/API_TESTING.md).

## Alert Consumer

Run the Event Hubs Kafka-compatible alert consumer:

```bash
./scripts/run-alert-consumer.sh
```

The consumer accepts either a raw Alertmanager webhook payload or an AIRP event envelope whose `payload` field contains the Alertmanager webhook body. It validates and deduplicates alerts before creating incidents.

Publish a sample alert into the configured Event Hubs topic:

```bash
./scripts/publish-sample-alert.py
```

The sample alert uses a stable fingerprint and incident idempotency key, so repeated publishes should map to one incident row while replay attempts are tracked as duplicates.

## Temporal Worker

Run the Temporal worker that owns incident workflows:

```bash
./scripts/run-temporal-worker.sh
```

When `AIRP_TEMPORAL_START_WORKFLOWS=true`, the alert consumer starts a durable workflow for every newly created incident and stores the workflow ID on the incident row.

## Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

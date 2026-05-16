# AIRP Enterprise Product Plan

## Product Vision

AIRP is an end-to-end Autonomous Incident Resolution Platform for Kubernetes-based enterprise microservices. It detects incidents, gathers operational and repository evidence, performs multi-agent root cause analysis, creates GitHub issues and Slack notifications, proposes remediation pull requests, waits for controlled human approval, and writes reusable RCA documentation back into organizational memory.

The product must feel like a polished SRE command center, not just a collection of agents. Every incident should have a clear timeline, evidence trail, owner, severity, RCA hypothesis, approval state, remediation artifact, and final learning record.

## Non-Negotiable Principles

- No production-changing action runs without a recorded approval.
- Every LLM answer must cite tool evidence from telemetry, Kubernetes, GitHub, historical incidents, or service metadata.
- Secrets are never stored in documentation, prompts, logs, GitHub issues, PR bodies, Slack messages, or embeddings.
- All agent decisions, model calls, MCP tool calls, approvals, and repository writes are audit logged.
- The system must degrade to human escalation instead of silently closing uncertain incidents.
- Workflows must be replayable, retryable, and idempotent.

## Source Inputs

- Architecture blueprint supplied in Eraser.io diagram-as-code syntax.
- Existing AIRP repository documentation and deployment notes.
- GenAI Hub starter code in `genaihub_startercode-main/GenAI Hub Starter`.
- Client GitHub organization: `https://github.com/orgs/AIRP-client`.
- Client runtime platform: Azure Kubernetes Service cluster `AIRP-cluster-high-per` in resource group `Semicolon-AIRP-rg`.
- Client delivery path: each AIRP-client repository builds a Docker image, pushes it to DockerHub, and the same image is deployed into AKS pods.
- Required agents: Monitoring, Correlation, RCA, Remediation, Documentation.
- Required tool integrations: Kubernetes MCP Server, GitHub MCP Server, Slack, GenAI Hub, PostgreSQL + pgvector, Redis, Kafka, Temporal.

## Client Environment Topology

The client environment is the product's main operating surface:

```text
AIRP-client GitHub Organization
  -> Multiple application repositories
  -> CI builds Docker images
  -> DockerHub image registry
  -> Azure AKS deployments
  -> Kubernetes pods running the same DockerHub images
  -> OpenTelemetry / Prometheus signals
  -> AIRP incident workflow
```

AIRP must preserve a reliable relationship between source code, container images, and live pods:

| Object | System of Record | Required Mapping |
|---|---|---|
| Source repository | AIRP-client GitHub organization | Repository URL, default branch, service owner, CODEOWNERS, service name. |
| Pull request / commit | GitHub MCP Server | Commit SHA, merged PR, changed files, author, merge time, release tag. |
| Container image | DockerHub | Image repository, tag, digest, build time, source commit SHA, SBOM link if available. |
| Runtime workload | Azure AKS / Kubernetes MCP Server | Namespace, deployment, replica set, pod, container image tag and digest. |
| Incident evidence | AIRP data store | Incident ID, service, pod, image digest, commit SHA, PR link, logs, events, metrics. |

The most important RCA join is:

```text
pod -> container image tag/digest -> DockerHub image -> source commit -> merged PR -> changed files -> probable root cause
```

If image metadata does not expose the source commit SHA, AIRP should fall back to release tags, deployment annotations, Helm values, Kubernetes labels, GitHub Actions build metadata, or PR merge windows.

## Azure AKS Access

Operators and the Kubernetes MCP Server need controlled access to the Azure-hosted AKS cluster.

Prerequisites:

- Azure CLI installed locally.
- `kubectl` and `kubelogin` installed through Azure CLI.
- User or workload identity authorized for subscription and AKS read access.

Local setup:

```bash
az login
az account set --subscription 568d5cd8-cd2c-4170-ae3e-0b93b2cc39aa
az aks install-cli
az aks get-credentials \
  --resource-group Semicolon-AIRP-rg \
  --name AIRP-cluster-high-per \
  --overwrite-existing
kubectl config current-context
kubectl get nodes
kubectl get pods --all-namespaces
```

If `az aks get-credentials` cannot find the resource group or cluster, first confirm which Azure subscription owns `Semicolon-AIRP-rg`, then rerun `az account set --subscription <subscription-id>` with the owning subscription.

Kubernetes MCP Server setup should use a dedicated identity instead of a developer's local credentials. MVP access should be read-only and limited to the namespaces that run AIRP-client services.

Required Kubernetes read scope:

- Pods, deployments, replica sets, services, config maps, events, namespaces, and logs.
- Container image tags and image IDs from pod specs and status.
- Rollout history and deployment annotations.
- Resource requests, limits, restart counts, readiness, liveness, and termination reasons.

Mutating cluster access is out of scope for MVP.

## GenAI Hub Starter Findings

The local GenAI Hub starter code confirms these integration patterns:

- GenAI Hub uses OpenAI-compatible APIs.
- Chat completions use `/v1/chat/completions`.
- Embeddings use `/v1/embeddings`.
- Direct Python integration uses `OpenAI(api_key=..., base_url=..., http_client=...)`.
- LangChain integration uses `ChatOpenAI(model=..., base_url=..., api_key=..., http_client=...)`.
- Embeddings use `openai_client.embeddings.create(model="embeddings", input=...)`.
- Environment variables used by the starter are `MODEL`, `GATEWAY_BASE_URL`, and `GATEWAY_API_KEY`.
- Corporate SSL environments may need `SSL_CERT_FILE` or `REQUESTS_CA_BUNDLE` and the Python 3.13+ X509 strict verification workaround shown in the starter.

AIRP should not copy the starter scripts directly into agent code. Instead, build a reusable `GenAIHubClient` adapter that follows the same connection pattern and adds production controls.

## GenAI Hub Configuration

The gateway URL is safe to store in config:

```text
GATEWAY_BASE_URL=https://hub-proxy-service.thankfulfield-16b4d5d6.eastus.azurecontainerapps.io
```

The API key must be stored only as a secret:

```text
GATEWAY_API_KEY=<stored in Kubernetes Secret or external secret manager>
```

Do not commit the raw API key to this repository.

## Available Models

| Model | Primary Use |
|---|---|
| `gpt-4.1` | Balanced production reasoning, summarization, issue and PR drafting. |
| `gpt-4.1-nano` | Fast, low-cost alert summarization, classification, lightweight validation. |
| `o3-mini` | Focused reasoning checks and fallback RCA reasoning. |
| `gpt-4o` | General multimodal-ready assistant behavior and operational summaries. |
| `embeddings` | pgvector incident memory, semantic search, historical RCA retrieval. |
| `anthropic.claude-sonnet-4` | Long-form documentation and high-quality narrative RCA drafts. |
| `gpt-5.1-CIO` | Advanced reasoning fallback for RCA and remediation planning. |
| `gpt-5.2-CIO` | Primary premium model for high-severity RCA and remediation planning. |
| `amazon.nova-micro-v1:0` | Low-latency short prompts. |
| `gemini-2.5-flash-lite` | Fast lightweight drafting and classification. |
| `amazon.nova-2-lite-v1:0` | Lightweight assistant workflows. |
| `amazon.nova-lite-v1:0` | Cost-sensitive general assistant tasks. |

## Per-Agent Model Routing

| Agent | Primary Model | Fallback Model | Temperature | Notes |
|---|---|---|---|---|
| Monitoring | `gpt-4.1-nano` | `gemini-2.5-flash-lite` | `0.0-0.1` | Use only for enrichment and classification; alert detection remains deterministic. |
| Correlation | `gpt-4.1` | `gpt-4o` | `0.1` | Uses `embeddings` for historical incident retrieval. |
| RCA | `gpt-5.2-CIO` | `gpt-5.1-CIO` or `o3-mini` | `0.0-0.2` | Highest evidence requirements; must cite Kubernetes and GitHub facts. |
| Remediation | `gpt-5.2-CIO` | `gpt-4.1` | `0.0-0.2` | Generates change plans, draft PRs, tests, and rollback plans. |
| Documentation | `gpt-4.1` | `anthropic.claude-sonnet-4` | `0.2-0.4` | Produces RCA reports, Slack summaries, wiki entries, and postmortems. |
| Embedding Jobs | `embeddings` | None | N/A | Used for incident memory and semantic search. |

## LLM Adapter Contract

Create a shared adapter, for example `agents/llm/genaihub_client.py`, with these responsibilities:

- Read `GATEWAY_BASE_URL` and `GATEWAY_API_KEY` from environment or secret-mounted config.
- Accept explicit `model`, `temperature`, `max_tokens`, `timeout`, and `request_id` parameters.
- Provide `chat()`, `structured_chat()`, and `embed()` methods.
- Support OpenAI-compatible direct calls and LangChain `ChatOpenAI` calls.
- Configure `httpx.Client` with SSL bundle support using `SSL_CERT_FILE` or `REQUESTS_CA_BUNDLE`.
- Redact secrets, tokens, credentials, IP allowlists, and customer payloads before model calls.
- Emit structured model telemetry: model, latency, prompt size, completion size, cost estimate, retry count, and failure reason.
- Store prompt template versions, model version names, and response hashes for auditability.
- Enforce JSON schema validation for agent outputs.
- Retry transient gateway failures with bounded exponential backoff.
- Route rate-limit failures to a cheaper fallback only when policy allows.

Example production shape:

```python
import os
import ssl

import httpx
from openai import OpenAI


def build_genaihub_client() -> OpenAI:
    ca_bundle = os.getenv("SSL_CERT_FILE", os.getenv("REQUESTS_CA_BUNDLE"))
    ssl_context = ssl.create_default_context(cafile=ca_bundle)
    ssl_context.verify_flags &= ~ssl.VERIFY_X509_STRICT

    return OpenAI(
        api_key=os.environ["GATEWAY_API_KEY"],
        base_url=os.environ["GATEWAY_BASE_URL"],
        http_client=httpx.Client(verify=ssl_context, timeout=60.0),
    )
```

## Target Architecture

```text
AIRP-client GitHub Org
  -> Client repositories
  -> DockerHub images
  -> Azure AKS cluster
  -> Kubernetes pods / Enterprise Microservices
  -> OpenTelemetry Collector
  -> Prometheus / Grafana
  -> Kafka
  -> Monitoring Agent
  -> Temporal Incident Workflow
  -> LangGraph / CrewAI Supervisor
  -> Correlation Agent
  -> RCA Agent
     -> Kubernetes MCP Server
     -> GitHub MCP Server
     -> Docker image / commit correlation
     -> Slack Notification
     -> GitHub Issue
  -> Remediation Agent
     -> GitHub MCP Server
     -> Approval Checkpoint
     -> Pull Request
  -> Documentation Agent
     -> Enterprise Wiki
     -> PostgreSQL + pgvector
```

## Eraser Diagram Source

```eraser
// Enterprise Architecture Blueprint: Autonomous Incident Resolution Platform
// Render via Eraser.io Diagram-as-Code Syntax

Target Ecosystem [color: outline] {
  "Enterprise Microservices" [icon: kubernetes, color: blue]
  "AIRP-client GitHub Org" [icon: github, color: black]
  "Client Repositories" [icon: git-branch, color: black]
  "DockerHub Image Registry" [icon: docker, color: blue]
  "Azure AKS Cluster" [icon: azure, color: blue]
  "Kubernetes Pods" [icon: box, color: blue]
  "Enterprise Wiki" [icon: book-open, color: green]
  "Slack Incident Channel" [icon: slack, color: purple]
}

Telemetry Layer [color: pastel] {
  "OpenTelemetry Collector" [icon: server, color: purple]
  "Prometheus" [icon: prometheus, color: red]
  "Grafana" [icon: grafana, color: orange]
}

Event Bus [color: plain] {
  "Kafka Message Broker" [icon: kafka, color: black]
}

AI Orchestration Layer [color: outline] {
  "Temporal Workflow Engine" [icon: gear, color: blue]

  Agentic Framework {
    "LangGraph / CrewAI Supervisor" [icon: cpu, color: purple]
    "Monitoring Agent" [icon: eye, color: teal]
    "Correlation Agent" [icon: git-merge, color: teal]
    "RCA Agent" [icon: search, color: teal]
    "Remediation Agent" [icon: tool, color: teal]
    "Documentation Agent" [icon: file-text, color: teal]
  }

  "GenAI Hub Gateway" [icon: openai, color: green]
}

Data Layer [color: plain] {
  "PostgreSQL + pgvector" [icon: postgresql, color: blue]
  "Redis Session Cache" [icon: database, color: red]
  "Audit Event Store" [icon: shield, color: gray]
}

Execution Layer [color: pastel] {
  "Kubernetes MCP Server" [icon: kubernetes, color: blue]
  "GitHub MCP Server" [icon: github, color: black]
  "Approval Checkpoint (Human-in-the-loop)" [icon: user, color: orange]
}

"Enterprise Microservices" > "OpenTelemetry Collector": "Traces, metrics, logs"
"AIRP-client GitHub Org" > "Client Repositories": "Multiple service repositories"
"Client Repositories" > "DockerHub Image Registry": "CI builds and pushes images"
"DockerHub Image Registry" > "Azure AKS Cluster": "Deployment image source"
"Azure AKS Cluster" > "Kubernetes Pods": "Runs client service pods"
"Kubernetes Pods" > "Enterprise Microservices": "Runtime workloads"
"OpenTelemetry Collector" > "Prometheus": "Metrics pipeline"
"Prometheus" <> "Grafana": "Dashboards and SLO views"
"Prometheus" > "Kafka Message Broker": "Anomaly alerts and webhooks"

"Kafka Message Broker" > "Monitoring Agent": "Async alert consumption"
"Monitoring Agent" > "Temporal Workflow Engine": "Start validated incident workflow"
"Temporal Workflow Engine" <> "LangGraph / CrewAI Supervisor": "Durable state and retries"

"LangGraph / CrewAI Supervisor" <> "Monitoring Agent"
"LangGraph / CrewAI Supervisor" <> "Correlation Agent"
"LangGraph / CrewAI Supervisor" <> "RCA Agent"
"LangGraph / CrewAI Supervisor" <> "Remediation Agent"
"LangGraph / CrewAI Supervisor" <> "Documentation Agent"
"LangGraph / CrewAI Supervisor" <> "GenAI Hub Gateway": "OpenAI-compatible LLM and embeddings"
"LangGraph / CrewAI Supervisor" <> "Redis Session Cache": "Ephemeral context"

"Correlation Agent" <> "PostgreSQL + pgvector": "Historical incident vector search"

"RCA Agent" <> "Kubernetes MCP Server": "Logs, events, pods, deployments, image IDs"
"RCA Agent" <> "GitHub MCP Server": "Commits, PR history, release metadata"
"Kubernetes MCP Server" <> "Azure AKS Cluster": "Read runtime state"
"Kubernetes MCP Server" <> "Kubernetes Pods": "Read logs and pod image digests"
"GitHub MCP Server" <> "AIRP-client GitHub Org": "Org-scoped repository access"
"GitHub MCP Server" <> "Client Repositories": "Read source and repository history"
"RCA Agent" <> "DockerHub Image Registry": "Map pod image to tag, digest, and source commit"
"RCA Agent" > "GitHub MCP Server": "Create RCA issue"
"RCA Agent" > "Slack Incident Channel": "Send incident notification"

"Remediation Agent" <> "GitHub MCP Server": "Prepare branch, diff, tests, PR"
"Remediation Agent" > "Approval Checkpoint (Human-in-the-loop)": "Request approval for repository write"
"Approval Checkpoint (Human-in-the-loop)" > "GitHub MCP Server": "Execute approved PR action"
"GitHub MCP Server" > "Client Repositories": "Create issue / draft PR"

"Documentation Agent" > "Enterprise Wiki": "Publish RCA and postmortem"
"Documentation Agent" > "PostgreSQL + pgvector": "Store report and embeddings"
"LangGraph / CrewAI Supervisor" > "Audit Event Store": "Agent, model, approval, and tool audit trail"
```

## Product Experience

### SRE Command Center

The web application should provide:

- Incident list filtered by severity, service, environment, owner, status, and confidence.
- Incident detail page with timeline, evidence, RCA hypotheses, affected AKS pods, container image tag/digest, related commits, linked GitHub issue, linked Slack thread, and remediation status.
- Approval queue for remediation PRs and risky repository actions.
- Service catalog with owner, AIRP-client repository, DockerHub image, AKS namespace, Kubernetes deployment, dashboards, runbooks, and SLO links.
- Historical RCA search backed by pgvector.
- Agent activity view showing what each agent did, which tools it called, and what evidence it used.
- Audit log page for compliance review.
- Admin settings for model routing, risk thresholds, service onboarding, Slack channels, and repository permissions.

### Slack Experience

The RCA Agent should create a Slack notification with:

- Incident title, severity, affected service, environment, and start time.
- Current status and owner.
- Top RCA hypothesis with confidence and evidence summary.
- Links to Grafana dashboard, GitHub issue, incident detail page, and relevant PRs.
- Clear next action: investigate, approve remediation, reject remediation, or escalate.

### GitHub Experience

The RCA Agent creates an issue. The Remediation Agent creates a PR after policy approval.

GitHub issue content should include:

- Incident summary.
- Affected services and customer impact.
- Affected AKS namespace, deployment, pods, and DockerHub image tag/digest.
- Evidence from Kubernetes logs/events and Prometheus metrics.
- Suspected root cause and confidence.
- Related commits, PRs, deployments, and releases.
- Recommended remediation path.
- Links to Slack thread, Grafana dashboard, incident page, and final RCA when available.

PR content should include:

- Problem statement.
- Root cause evidence.
- Affected DockerHub image and source commit relationship.
- Proposed code/config change.
- Test plan.
- Rollback plan.
- Risk level.
- Approval record link.
- Related GitHub issue.

## End-to-End Incident Flow

1. AIRP-client repositories build Docker images and publish them to DockerHub.
2. Azure AKS deployments run those DockerHub images as Kubernetes pods.
3. Microservices emit traces, logs, and metrics through OpenTelemetry.
4. Prometheus evaluates alert rules and emits anomaly events into Kafka.
5. The Monitoring Agent consumes `airp.alerts.raw`, validates the alert, deduplicates it, enriches it with service metadata, and starts a Temporal workflow.
6. Temporal creates a durable incident workflow and calls the LangGraph / CrewAI Supervisor.
7. The Supervisor asks the Correlation Agent to retrieve historical incidents, similar error signatures, service topology, repository metadata, image metadata, and recent alert clusters.
8. The RCA Agent queries the Kubernetes MCP Server for pod logs, restart counts, events, deployment status, resource pressure, namespace-level context, container image tags, and image IDs.
9. The RCA Agent maps the running pod image to DockerHub tag/digest and then to the AIRP-client repository commit or PR that produced the image.
10. The RCA Agent queries the GitHub MCP Server for recent commits, merged PRs, touched files, release tags, deployments, owners, and prior related issues.
11. The RCA Agent uses GenAI Hub to produce ranked root cause hypotheses with explicit evidence citations.
12. The RCA Agent creates a GitHub issue in the relevant AIRP-client repository and sends a Slack incident notification with the top hypothesis and evidence links.
13. The Remediation Agent reads the RCA issue, repository context, Docker image context, and service policy, then prepares a remediation plan.
14. The system requests human approval for any repository write or production-impacting action.
15. After approval, the Remediation Agent uses the GitHub MCP Server to create a branch and pull request in the relevant AIRP-client repository.
16. CI runs tests, builds a replacement Docker image, and policy checks validate the PR.
17. The Documentation Agent publishes the final RCA report, stores embeddings, and updates incident history.
18. The incident closes only after the workflow records status, evidence, actions, image mapping, links, and follow-up tasks.

## Agent Contracts

### Monitoring Agent

Input:

- Kafka alert event from `airp.alerts.raw`.
- Prometheus labels and alert annotations.
- Service catalog metadata.

Responsibilities:

- Validate event schema.
- Deduplicate noisy alerts.
- Normalize severity, service, namespace, environment, and owner.
- Attach AKS namespace, deployment, pod, and container image metadata when available.
- Attach Grafana and Prometheus links.
- Start or update the Temporal workflow.
- Use LLM only for lightweight classification or summary enrichment.

Output:

- `IncidentCandidate` record.
- `airp.incidents.validated` event.
- Temporal workflow start signal.

### Correlation Agent

Input:

- Validated incident.
- Service metadata.
- Recent alert cluster.
- Historical incident memory.

Responsibilities:

- Retrieve similar incidents through pgvector.
- Compare symptoms, service topology, time windows, repository history, image versions, and known failure modes.
- Rank related incidents by recency, similarity, service ownership, and resolution quality.
- Provide compact context to RCA Agent.

Output:

- Correlation packet with related incidents, probable dependencies, duplicate candidates, and prior remediation outcomes.

### RCA Agent

Input:

- Correlation packet.
- Prometheus/Grafana links.
- Kubernetes MCP tool access.
- GitHub MCP tool access.
- GenAI Hub LLM access.

Responsibilities:

- Query Kubernetes MCP Server for logs, events, pod state, deployment rollout state, resource pressure, restart history, image tags, and image IDs.
- Map AKS pod image tag/digest to DockerHub image and AIRP-client source repository.
- Query GitHub MCP Server for recent commits, merged PRs, deployment references, touched files, owners, and linked issues in the relevant AIRP-client repository.
- Compare error logs with recent code and configuration changes.
- Generate ranked root cause hypotheses with supporting and contradicting evidence.
- Create a GitHub issue in the affected AIRP-client repository for confirmed or likely incidents.
- Send Slack notification to the incident channel.
- Escalate to human when confidence is low or evidence conflicts.

Output:

- `RcaReport` with hypotheses, evidence, confidence, blast radius, related commits, issue link, Slack message link, and remediation recommendation.

### Remediation Agent

Input:

- RCA report.
- GitHub issue.
- Repository context.
- Service risk policy.
- Approval state.

Responsibilities:

- Decide whether remediation should be code, config, rollback, runbook, or escalation.
- Generate a minimal, reviewable change plan.
- Prepare branch, diff, tests, and rollback plan in the affected AIRP-client repository through GitHub MCP Server.
- Create PR only when policy allows the write action and approval is recorded for production-risk actions.
- Keep generated changes small and tied to the RCA issue.
- Ensure the PR path triggers the repository's DockerHub image build pipeline before AKS rollout.

Output:

- `RemediationPlan`.
- Draft or ready-for-review pull request.
- Test plan and rollback plan.

### Documentation Agent

Input:

- Incident timeline.
- RCA report.
- GitHub issue and PR links.
- Slack thread.
- Approval and remediation outcome.

Responsibilities:

- Produce final RCA report.
- Publish to enterprise wiki.
- Store structured incident summary in PostgreSQL.
- Create embeddings for searchable memory.
- Generate follow-up tasks for prevention work.

Output:

- Published RCA document.
- Updated incident memory.
- Closed incident event.

## MCP Tooling and Permissions

| Tool | Read Permissions | Write Permissions | Production Guardrail |
|---|---|---|---|
| Kubernetes MCP Server | AKS pods, events, logs, deployments, replica sets, services, config maps, rollout status, container image IDs | None for MVP | Mutating cluster actions are disabled until explicitly approved in a later release. |
| GitHub MCP Server | AIRP-client org repositories, files, commits, branches, PRs, issues, checks, releases | Create issues, create branches, create draft PRs, comment on issues/PRs | No merge, force-push, destructive branch action, or secret access. |
| DockerHub Registry | Image repositories, tags, digests, labels, build metadata | None for MVP | Used only to correlate running AKS images with source commits and PRs. |
| Slack Integration | Channel metadata, message thread links | Send incident notifications and approval prompts | Approval payload must be signed and stored before execution. |
| GenAI Hub Gateway | Model calls and embeddings | None | Redaction, schema validation, model telemetry, and prompt versioning required. |

## Workflow State Model

Temporal owns durable state and retries.

```text
RECEIVED
VALIDATED
CORRELATED
RCA_COLLECTING_K8S_EVIDENCE
IMAGE_CORRELATED
RCA_COLLECTING_GITHUB_EVIDENCE
RCA_IN_PROGRESS
RCA_ISSUE_CREATED
SLACK_NOTIFIED
REMEDIATION_PLANNED
WAITING_FOR_APPROVAL
APPROVED
PR_CREATED
CI_VALIDATING
DOCUMENTING
CLOSED
ESCALATED
```

Rules:

- Activities must be idempotent.
- Tool calls must include incident ID and idempotency key.
- Failed non-critical documentation publishing retries without reopening the incident.
- Failed RCA or remediation escalates with the evidence bundle.
- Approval expiration moves the workflow to `ESCALATED`.

## Kafka Topic Plan

| Topic | Producer | Consumer | Purpose |
|---|---|---|---|
| `airp.alerts.raw` | Prometheus / Alertmanager bridge | Monitoring Agent | Raw alert stream. |
| `airp.incidents.validated` | Monitoring Agent | Temporal starter | Deduplicated incident candidates. |
| `airp.agent.events` | Supervisor and agents | Audit, dashboard, analytics | Agent progress and decisions. |
| `airp.tool.calls` | MCP adapters | Audit, dashboard | Kubernetes, GitHub, Slack, and LLM tool traces. |
| `airp.remediation.proposed` | Remediation Agent | Approval service | Human-reviewable remediation proposal. |
| `airp.approvals.recorded` | Approval service | Temporal workflow | Signed approval or rejection result. |
| `airp.incidents.closed` | Documentation Agent | Analytics, reporting | Final incident outcome. |
| `airp.deadletter` | All consumers | Operations | Malformed or repeatedly failing events. |

## Canonical Event Fields

Every event should include:

```json
{
  "schema_version": "1.0",
  "event_id": "uuid",
  "incident_id": "uuid",
  "correlation_id": "uuid",
  "event_type": "airp.incident.validated",
  "timestamp": "2026-05-16T00:00:00Z",
  "service": "checkout-api",
  "namespace": "production",
  "environment": "prod",
  "severity": "critical",
  "producer": "monitoring-agent",
  "payload": {}
}
```

## Data Model

| Table | Purpose |
|---|---|
| `services` | Service catalog: owner, namespace, repo, Slack channel, SLO links, dashboards, runbooks. |
| `repositories` | AIRP-client repository metadata: URL, default branch, owners, CI workflow, DockerHub image name. |
| `container_images` | DockerHub image repository, tag, digest, build timestamp, source commit SHA, and SBOM/provenance links. |
| `runtime_workloads` | AKS namespace, deployment, replica set, pod, container, image tag, image ID, node, and rollout revision. |
| `incidents` | Incident identity, state, severity, service, environment, ownership, timestamps, and closure metadata. |
| `incident_events` | Timeline of alerts, agent actions, tool calls, approvals, PRs, comments, and state transitions. |
| `evidence_items` | Kubernetes logs/events, Prometheus query results, GitHub commits/PRs, deployment data, and links. |
| `rca_hypotheses` | Ranked hypotheses, confidence, supporting evidence, contradicting evidence, and model metadata. |
| `github_artifacts` | Created issues, branches, PRs, comments, checks, and linked commits. |
| `slack_messages` | Notification message IDs, channels, thread IDs, and approval interactions. |
| `remediation_plans` | Proposed actions, risk, tests, rollback plan, approval state, PR link, and outcome. |
| `approvals` | Approver, decision, timestamp, signed payload hash, requested action, and expiry. |
| `model_calls` | Model, prompt template version, token counts, latency, response hash, and validation result. |
| `tool_calls` | MCP server, tool name, parameters hash, result hash, latency, and error details. |
| `incident_embeddings` | pgvector embeddings for symptoms, RCA summaries, fixes, and postmortem text. |

Redis stores short-lived context:

| Key Pattern | Purpose | TTL |
|---|---|---|
| `incident:{id}:session` | Active supervisor scratch state | 24 hours |
| `incident:{id}:dedupe` | Duplicate alert suppression | 1-6 hours |
| `service:{name}:metadata` | Service catalog cache | 15-60 minutes |
| `approval:{id}:nonce` | Approval replay protection | Until approval expiry |

## API Surface

| Endpoint | Purpose |
|---|---|
| `POST /api/incidents` | Create incident from validated alert or manual report. |
| `GET /api/incidents` | List incidents with filters. |
| `GET /api/incidents/{id}` | Incident detail, timeline, evidence, RCA, and remediation state. |
| `POST /api/incidents/{id}/signals` | Send workflow signal such as escalate, pause, resume, or close. |
| `POST /api/incidents/{id}/approvals` | Record approval or rejection. |
| `GET /api/incidents/{id}/audit` | Audit trail for compliance. |
| `GET /api/services` | Service catalog. |
| `POST /api/services` | Onboard or update service metadata. |
| `GET /api/repositories` | AIRP-client repository and DockerHub image mapping. |
| `GET /api/workloads` | AKS workload, pod, and image inventory. |
| `GET /api/search/incidents` | Semantic RCA search. |
| `GET /api/health` | Platform health. |

## Configuration Example

```yaml
client:
  github_org: AIRP-client
  github_org_url: https://github.com/orgs/AIRP-client
  repository_discovery: org_repositories
  image_registry: dockerhub

azure:
  subscription_id: 568d5cd8-cd2c-4170-ae3e-0b93b2cc39aa
  resource_group: Semicolon-AIRP-rg
  aks_cluster_name: AIRP-cluster-high-per

dockerhub:
  required_image_metadata:
    - image_repository
    - tag
    - digest
    - source_commit_sha
    - build_timestamp

llm:
  gateway_base_url_env: GATEWAY_BASE_URL
  gateway_api_key_secret_ref: genaihub-secrets/GATEWAY_API_KEY
  default_timeout_seconds: 60
  ssl:
    cert_file_env: SSL_CERT_FILE
    requests_ca_bundle_env: REQUESTS_CA_BUNDLE
  models:
    monitoring: gpt-4.1-nano
    correlation: gpt-4.1
    rca: gpt-5.2-CIO
    rca_fallback: gpt-5.1-CIO
    remediation: gpt-5.2-CIO
    documentation: gpt-4.1
    embeddings: embeddings

policy:
  min_rca_confidence_for_remediation: 0.78
  require_approval_for_prod_pr: true
  require_approval_for_issue_creation: false
  approval_ttl_minutes: 60
  max_changed_files_per_ai_pr: 5
  block_secret_like_content_in_prompts: true

integrations:
  kubernetes_mcp:
    cloud: azure_aks
    cluster_name: AIRP-cluster-high-per
    read_only: true
    required_scopes:
      - pods
      - logs
      - events
      - deployments
      - replicasets
  github_mcp:
    org: AIRP-client
    allow_create_issue: true
    allow_create_branch: true
    allow_create_pr: true
    allow_merge_pr: false
  dockerhub:
    read_only: true
    use_digest_for_correlation: true
  slack:
    incident_channel: "#airp-incidents"
```

## Implementation Roadmap

### Phase 1: Product Foundation

- Define service catalog schema and onboarding flow.
- Discover AIRP-client GitHub repositories and map each repository to its DockerHub image name.
- Store Azure AKS namespace, deployment, and service ownership metadata.
- Add centralized configuration for environments, secrets, model routing, and risk policy.
- Create the incident API skeleton and health checks.
- Add audit event conventions and correlation IDs.

Deliverable: AIRP can register services, map repository-to-image-to-AKS workload ownership, and create a manual incident with an auditable state record.

### Phase 2: GenAI Hub Adapter

- Implement shared `GenAIHubClient` using the starter code connection pattern.
- Add chat, structured output, and embedding methods.
- Add prompt templates for each agent.
- Add model routing, fallback policy, retries, timeouts, and telemetry.
- Add redaction and prompt/response schema validation.

Deliverable: All agents can call GenAI Hub through one production-safe adapter.

### Phase 3: Observability and Kafka Ingestion

- Instrument target services through OpenTelemetry.
- Configure Prometheus alerts and Grafana dashboards.
- Add Alertmanager or webhook bridge that publishes to Kafka.
- Implement Monitoring Agent alert validation and deduplication.
- Add dead-letter handling.

Deliverable: A real or synthetic alert becomes one validated incident candidate.

### Phase 4: Temporal Workflow and Supervisor

- Deploy Temporal and define incident workflow states.
- Implement workflow activities for each agent.
- Implement LangGraph / CrewAI Supervisor routing and typed state.
- Emit progress to `airp.agent.events`.

Deliverable: Incidents progress durably through monitoring, correlation, RCA, remediation, and documentation.

### Phase 5: Correlation and Incident Memory

- Enable PostgreSQL + pgvector.
- Store historical incident summaries and embeddings.
- Implement similarity search for symptoms, error text, service, and remediation outcome.
- Add correlation ranking and duplicate detection.

Deliverable: RCA starts with relevant historical context and prior outcomes.

### Phase 6: RCA with Kubernetes and GitHub MCP

- Deploy Kubernetes MCP Server with read-only permissions.
- Deploy GitHub MCP Server with least-privilege repository permissions.
- Configure GitHub MCP Server for the AIRP-client organization and its service repositories.
- Implement RCA evidence collectors for logs, events, deployment state, container image IDs, DockerHub tags/digests, commits, PRs, issues, and release metadata.
- Add image correlation from AKS pod image to DockerHub digest to GitHub commit or merged PR.
- Create GitHub issue templates and Slack notification templates.
- Require evidence citations in every RCA hypothesis.

Deliverable: RCA Agent creates a GitHub issue and Slack notification backed by Kubernetes and GitHub evidence.

### Phase 7: Remediation PR Workflow

- Implement Remediation Agent planning.
- Create branch and PR generation through GitHub MCP Server.
- Attach tests, rollback plan, risk rating, and approval record.
- Enforce approval gate before production-risk repository writes.
- Integrate CI status into the incident timeline.

Deliverable: Approved incidents produce small, reviewable remediation PRs linked to the RCA issue.

### Phase 8: Documentation and Learning Loop

- Generate final RCA reports.
- Publish to enterprise wiki.
- Store report, evidence, and embeddings.
- Add post-incident metrics: MTTD, MTTA, MTTR, false positive rate, remediation success rate.

Deliverable: Every closed incident improves future correlation and RCA.

### Phase 9: SRE Command Center

- Build incident list, incident detail, approval queue, service catalog, audit log, and semantic RCA search.
- Add deep links to Grafana, Slack, GitHub, Temporal, and Kubernetes evidence.
- Add admin controls for model routing and risk policies.

Deliverable: SRE users can manage incidents from one polished product UI.

### Phase 10: Production Hardening

- Add load tests, workflow replay tests, model evals, and chaos tests.
- Add backup/restore for PostgreSQL.
- Add Kafka retention and replay runbooks.
- Add secret rotation and gateway key expiry runbooks.
- Add compliance exports for audits.

Deliverable: AIRP is ready for production rollout with operational runbooks.

## Release Plan

### MVP

- Prometheus or Alertmanager to Kafka ingestion.
- Monitoring Agent validation and dedupe.
- Temporal workflow.
- GenAI Hub adapter.
- Correlation Agent with pgvector.
- RCA Agent with Kubernetes MCP and GitHub MCP read access.
- AIRP-client repository discovery and DockerHub image mapping.
- AKS pod image tag/digest capture.
- GitHub issue creation.
- Slack notification.
- Documentation Agent with stored RCA report.

### Beta

- Remediation Agent creates draft PRs.
- Human approval checkpoint.
- SRE command center incident detail page.
- Audit log UI.
- CI status integration.
- Service catalog onboarding UI.
- Repository, DockerHub image, and AKS workload inventory views.

### GA

- Full approval queue.
- Enterprise wiki publishing.
- Policy-based model routing.
- Cost and token dashboards.
- Multi-team service ownership.
- Incident replay and simulation tools.
- Compliance-ready audit exports.

## Acceptance Criteria

- A synthetic production alert creates exactly one incident workflow.
- The incident contains service, owner, severity, environment, Grafana link, AKS namespace, pod, image tag/digest, and correlation ID.
- The affected pod image maps back to a DockerHub image and the most likely AIRP-client repository commit or PR.
- The RCA Agent retrieves Kubernetes logs/events and GitHub commits/merged PRs for the affected time window.
- The RCA Agent creates a GitHub issue with evidence-backed hypotheses.
- The RCA Agent sends a Slack notification with incident links and top hypothesis.
- The Remediation Agent creates a PR only when policy permits and required approval exists.
- Every GitHub issue, Slack message, and PR is linked back to the incident.
- Every LLM output validates against a schema before it changes workflow state.
- Secrets are redacted from prompts, logs, Slack messages, issues, PRs, and embeddings.
- The Documentation Agent publishes and embeds the final RCA report.
- Temporal can resume the workflow after worker restart.
- Kafka replay can reprocess events without duplicate GitHub issues or PRs.
- The audit trail can explain who or what made every decision.

## Quality and Evaluation Plan

- Unit tests for schema validation, dedupe keys, prompt redaction, event contracts, and policy checks.
- Integration tests for Kafka, Temporal, PostgreSQL, Redis, Kubernetes MCP, GitHub MCP, Slack, and GenAI Hub adapter.
- Golden incident tests for known failure modes: crash loop, bad config, high latency, database exhaustion, memory leak, and failed deployment.
- LLM evals for groundedness, evidence citation quality, confidence calibration, and hallucination resistance.
- PR generation tests that check diff size, linked issue, rollback plan, and test plan.
- Security tests for secret leakage, approval replay, unauthorized MCP writes, and prompt injection.
- Load tests for alert bursts and concurrent incidents.
- Chaos tests for Temporal worker restart, Kafka consumer restart, GenAI Hub timeout, and MCP server outage.

## Security Requirements

- Store `GATEWAY_API_KEY`, GitHub tokens, Slack tokens, database passwords, and Kafka credentials in Kubernetes Secrets or external secret manager.
- Mount secrets as environment variables only into workloads that need them.
- Use separate service accounts per agent where practical.
- Use read-only Kubernetes MCP credentials for MVP.
- Use least-privilege GitHub credentials scoped to the AIRP-client organization repositories.
- Use DockerHub credentials only if private image metadata requires authentication; prefer read-only token scope.
- Block LLM access to raw secrets, credentials, authorization headers, and private keys.
- Sign approval payloads and verify payload hashes before execution.
- Log parameter hashes for sensitive tool calls instead of raw values.
- Require branch protection and CI before PR merge.
- Prevent generated PRs from modifying workflow security policy, secrets, or approval enforcement without human review.

## Reliability Requirements

- Kafka topics have retention long enough for replay after downstream outages.
- Temporal workflows use idempotency keys for GitHub issue, Slack message, and PR creation.
- PostgreSQL is backed up and migration-managed.
- Redis is treated as disposable cache, not source of truth.
- MCP outages cause retry or escalation, not partial closure.
- Image correlation failures do not block incident creation, but must be visible as missing evidence in RCA.
- GenAI Hub rate limits trigger retry, fallback, or escalation based on severity.
- Documentation publishing failures retry independently after urgent incident handling completes.

## Operational Runbooks

- Rotate GenAI Hub API key.
- Onboard a new service.
- Connect local operator machine to Azure AKS.
- Configure Kubernetes MCP Server for AKS read-only access.
- Configure GitHub MCP Server for the AIRP-client organization.
- Refresh repository-to-DockerHub-to-AKS workload mappings.
- Reprocess an incident from Kafka.
- Manually escalate a low-confidence RCA.
- Disable remediation PR creation.
- Recover from GitHub MCP outage.
- Recover from Kubernetes MCP outage.
- Restore PostgreSQL incident history.
- Tune model routing and fallback policy.
- Audit all actions for a specific incident.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Alert noise creates duplicate incidents | Deterministic dedupe key plus Temporal idempotency. |
| LLM produces unsupported RCA | Evidence citation requirements and schema validation. |
| Prompt injection from logs or GitHub content | Treat external text as untrusted evidence; isolate instructions from evidence. |
| Secret leakage into prompts or embeddings | Redaction middleware and secret-pattern blocking. |
| Unsafe remediation PR | Approval gate, branch protection, small diff limits, tests, rollback plan. |
| GitHub issue or PR duplicated on replay | Store idempotency keys and artifact links in PostgreSQL. |
| Running pod image cannot be mapped to a commit | Require image labels/build metadata; fall back to release tags, deployment annotations, and PR merge windows. |
| GitHub org contains many repos with inconsistent conventions | Maintain service catalog ownership and require repo/image metadata during onboarding. |
| GenAI Hub gateway outage | Retry, model fallback, or human escalation based on severity. |
| Historical RCA memory becomes stale | Rank by recency, service match, and successful remediation outcome. |
| MCP permissions too broad | Separate read/write identities and enforce policy in adapter. |

## Migration from Current AIRP Repository

The current repository already includes useful foundations: AIRP agent service documentation, PostgreSQL deployment, Prometheus stack notes, n8n workflow setup, and approval-oriented remediation flow.

The polished target product evolves that foundation by:

- Adding a production GenAI Hub adapter based on `genaihub_startercode-main`.
- Treating the AIRP-client GitHub organization as the repository boundary for GitHub MCP.
- Mapping AIRP-client repositories to DockerHub images and Azure AKS workloads.
- Moving from direct workflow coupling to Kafka-backed alert ingestion.
- Moving durable orchestration to Temporal.
- Using LangGraph / CrewAI as the explicit multi-agent supervisor.
- Adding Kubernetes MCP Server as the runtime evidence source for RCA.
- Adding GitHub MCP Server as the repository evidence and PR creation boundary.
- Using Slack as a first-class incident notification and approval surface.
- Extending PostgreSQL with pgvector for incident memory.
- Adding Redis only for ephemeral workflow context.
- Adding a polished SRE command center UI.
- Preserving human approval as the mandatory production safety checkpoint.

## External References

- AIRP-client GitHub organization: `https://github.com/orgs/AIRP-client`
- Azure CLI installation: `https://learn.microsoft.com/en-us/cli/azure/install-azure-cli?view=azure-cli-latest`
- Azure AKS CLI commands: `https://learn.microsoft.com/en-us/cli/azure/aks?view=azure-cli-latest`

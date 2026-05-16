# AIRP Production Completion Plan

This document tracks the remaining work to turn the current AIRP backend/API into a complete, production-ready, end-to-end Autonomous Incident Resolution Platform.

AIRP remains backend/API only. No frontend command center is planned in this backlog.

## Current Baseline

Already implemented:

- FastAPI backend scaffold with modular routes, services, schemas, and settings.
- Microsoft Entra ID authentication boundary.
- SQLAlchemy async models for catalog, repositories, workloads, incidents, events, evidence, approvals, remediation plans, model calls, tool calls, GitHub artifacts, Slack messages, and embeddings.
- Alembic initial schema plus incident idempotency migration.
- REST APIs for health, incidents, timelines, audit, services, repositories, workloads, approvals, remediation plans, and search.
- GenAI Hub adapter with OpenAI-compatible chat, structured chat, embeddings, redaction, retries, and model routing settings.
- Integration boundaries for GitHub MCP, Kubernetes MCP, Slack, and DockerHub.
- Azure Event Hubs Kafka-compatible configuration and JSON event publishing.
- Alertmanager payload normalization.
- Alert ingestion worker for Event Hubs Kafka raw alert topic.
- Redis alert dedupe and PostgreSQL incident idempotency key.
- Dead-letter publishing for malformed alert messages.
- Sample alert publisher script.
- Temporal workflow MVP with workflow IDs on incidents, worker entrypoint, basic workflow state, database status activity, and API workflow signals.
- LangGraph dependency, `src/airp/agents/` package, supervisor skeleton, Monitoring Agent node, Embedding Agent node, and Temporal `agent_graph_run` activity hook.
- Dockerfile, Docker Compose, Helm chart, AKS helper script, migration script, deployment docs, and verification script.
- Unit and smoke tests for the implemented foundation.

Still not production complete:

- Full Temporal workflow execution is not complete beyond the MVP workflow skeleton.
- LangGraph supervisor MVP is implemented, but full multi-agent graph orchestration remains pending.
- Real Kubernetes MCP, GitHub MCP, Slack, and GenAI agent behavior is not end-to-end.
- PostgreSQL + pgvector has not been fully verified with migrations and integration tests.
- Entra ID authorization roles are not production-grade yet.
- Observability, security hardening, CI/CD, and AKS production deployment need to be finished.

## Verified Agent-Orchestration Status

Verified from the current repository:

- `langgraph` is listed in `pyproject.toml`.
- `src/airp/agents/` exists.
- Monitoring Agent is implemented as a LangGraph node with structured output validation.
- Embedding Agent is implemented as a LangGraph node with redaction before embedding calls.
- RCA, Documentation, Remediation, and Correlation agents are not implemented as LangGraph nodes yet.
- Current Temporal workflow invokes a LangGraph supervisor through the `agent_graph_run` activity.
- Current GenAI Hub integration is used as an optional LLM/embedding adapter; production prompt templates and model-call persistence are still pending.

## Product Guardrails

- Backend/API only.
- Microsoft Entra ID is the only user authentication mechanism.
- Azure Event Hubs Kafka-compatible endpoint is the async event bus.
- AIRP-client GitHub organization is the target GitHub scope.
- AIRP-client DockerHub images are public and should be mapped to running AKS workloads.
- Kubernetes target is the Azure AKS cluster.
- GenAI Hub gateway configuration must come from environment variables or Kubernetes secrets.
- No API keys, connection strings, Slack tokens, GitHub tokens, kubeconfigs, or private secrets should be committed.
- Agents must be orchestrated through LangGraph, evidence-backed, structured-output driven, idempotent, auditable, and approval-gated before repository writes.

## Recommended Build Order

1. Stabilize persistence and API hardening.
2. Implement Temporal workflow engine and worker.
3. Wire validated alerts into workflows.
4. Implement read-only discovery and evidence collection through Kubernetes MCP, GitHub MCP, and DockerHub.
5. Implement LangGraph-based structured GenAI agents.
6. Add Slack notifications and approval callbacks.
7. Add governed GitHub issue and draft PR creation.
8. Add incident memory with pgvector.
9. Harden security, observability, CI/CD, and AKS deployment.
10. Prove the product with end-to-end incident simulations.

## Phase 1: Persistence and API Hardening

Goal: make the backend reliable against real PostgreSQL and ready for production users.

Tasks:

- [ ] Verify `alembic upgrade head` against PostgreSQL 16.
- [ ] Verify `0002_incident_idempotency` migration against PostgreSQL.
- [ ] Add `CREATE EXTENSION IF NOT EXISTS vector` migration for pgvector.
- [ ] Confirm embedding dimensions returned by GenAI Hub `embeddings`.
- [ ] Convert `incident_embeddings.vector` from JSON to `pgvector.Vector`.
- [ ] Add repository-layer classes for incident, catalog, approval, evidence, model-call, tool-call, GitHub artifact, and Slack message queries.
- [ ] Add pagination response shape: `items`, `limit`, `offset`, `total`.
- [ ] Update list APIs to return paginated responses.
- [ ] Add update endpoints for services, repositories, workloads, incidents, remediation plans, and approvals where appropriate.
- [ ] Add archive semantics for service catalog, repositories, workloads, and stale records.
- [ ] Add database check constraints for incident status, severity, remediation status, risk level, and approval decision.
- [ ] Add optimistic concurrency checks for approval-sensitive writes.
- [ ] Add request ID and correlation ID middleware.
- [ ] Return request/correlation IDs in every API response.
- [ ] Add structured audit event creation to every mutating API route.
- [ ] Add OpenAPI examples for key request and response models.
- [ ] Add PostgreSQL integration test profile using Docker Compose.
- [ ] Add migration smoke tests in CI.

Acceptance criteria:

- Empty PostgreSQL database migrates successfully.
- Current schema works with PostgreSQL, not only lightweight service tests.
- Duplicate alert replay creates one incident row.
- Every mutation creates a queryable audit event.
- API list endpoints support total counts and pagination.

## Phase 2: Microsoft Entra ID Authorization

Goal: enforce enterprise authentication and role-based authorization.

Tasks:

- [ ] Add issuer discovery from Entra `/.well-known/openid-configuration`.
- [ ] Cache JWKS and refresh on key rotation.
- [ ] Validate `aud`, `iss`, `exp`, `iat`, `nbf`, `tid`, and app roles.
- [ ] Define app roles: `AIRP.Admin`, `AIRP.SRE`, `AIRP.Viewer`, `AIRP.Approver`.
- [ ] Add route-level role dependencies.
- [ ] Require Admin for catalog/admin operations.
- [ ] Require SRE or Admin for incident mutation.
- [ ] Require Approver or Admin for approval decisions.
- [ ] Allow Viewer read-only access.
- [ ] Add signed JWT fixtures for tests.
- [ ] Test missing, expired, wrong-audience, wrong-issuer, and insufficient-role tokens.
- [ ] Document Entra app registration, scopes, roles, and local token acquisition.
- [ ] Fail fast in production when auth config is missing.

Acceptance criteria:

- Protected routes reject invalid tokens.
- Viewers cannot mutate state.
- Approvers can approve or reject approval requests.
- Admin can manage policy and catalog.

## Phase 3: Event Hubs Alert Ingestion Productionization

Goal: take the implemented alert ingestion code to production operation.

Tasks:

- [ ] Provision Event Hubs topics for raw alerts, validated incidents, agent events, and dead letters.
- [ ] Validate consumer connectivity against Azure Event Hubs Kafka endpoint.
- [ ] Validate sample alert publisher against the real raw alert topic.
- [ ] Package alert consumer as a separate Kubernetes Deployment.
- [ ] Add Helm template support for API, alert consumer, and future Temporal worker deployments.
- [ ] Add consumer liveness/readiness checks.
- [ ] Add consumer lag, processed count, duplicate count, and dead-letter count metrics.
- [ ] Add replay runbook for raw alerts.
- [ ] Add dead-letter replay or inspection tooling.
- [ ] Add integration test using a local Kafka-compatible broker or test container when available.

Acceptance criteria:

- A sample Alertmanager payload published to Event Hubs creates exactly one AIRP incident.
- Replaying the same message does not create a duplicate incident.
- Malformed messages land in dead-letter with enough context to debug.

## Phase 4: Temporal Workflow Execution

Goal: make incident lifecycle durable, restart-safe, and signalable.

Tasks:

- [x] Add Temporal settings: address, namespace, task queue, TLS options, and timeout defaults.
- [x] Add Temporal client factory.
- [x] Add Temporal worker entrypoint.
- [x] Implement `IncidentWorkflow`.
- [x] Start a workflow when an alert creates a validated incident.
- [x] Persist workflow ID and run ID on incidents.
- [ ] Add workflow states for received, validated, correlation, RCA, issue creation, Slack notification, remediation planning, approval wait, PR creation, documentation, closure, and escalation.
- [x] Implement workflow activities for database state updates.
- [ ] Implement workflow activities for correlation, Kubernetes evidence, GitHub evidence, GenAI RCA, GitHub issue creation, Slack notifications, remediation planning, approval handling, PR creation, documentation, and closure.
- [x] Add workflow signals: pause, resume, approve, reject, escalate, close.
- [ ] Add workflow signal for retry failed activity.
- [x] Add workflow query for current state and current step.
- [ ] Add workflow queries for evidence summary, approval request, and timeline.
- [ ] Add idempotency keys for every activity that writes external artifacts.
- [ ] Add retry policies with backoff and non-retryable error types.
- [ ] Add activity timeouts and heartbeat handling for long evidence collection.
- [ ] Add workflow replay tests.
- [ ] Add worker restart tests.

Acceptance criteria:

- Validated incident starts a Temporal workflow.
- Worker restart does not lose incident progress.
- Approval timeout escalates incident.
- Workflow state and database state remain consistent.

## Phase 5: Service Catalog and Environment Discovery

Goal: automatically understand AIRP-client repositories, DockerHub images, and AKS workloads.

Tasks:

- [ ] Implement AIRP-client GitHub organization repository discovery.
- [ ] Capture repository name, URL, default branch, owner team, topics, archived state, and visibility.
- [ ] Parse CODEOWNERS where available.
- [ ] Infer DockerHub image names from repository metadata, Dockerfiles, manifests, and conventions.
- [ ] Implement DockerHub public image tag listing.
- [ ] Implement DockerHub digest lookup for image tags.
- [ ] Implement AKS workload inventory sync through Kubernetes MCP.
- [ ] Capture namespace, deployment, replica set, pod, container, image, image tag, image ID, digest, node, readiness, restart count, and labels.
- [ ] Persist repository-to-image-to-workload mappings.
- [ ] Detect running image with no known repository.
- [ ] Detect repository image not running in AKS.
- [ ] Add scheduled discovery worker.
- [ ] Add manual refresh API endpoint.
- [ ] Add discovery audit events.
- [ ] Add tests with GitHub, DockerHub, and Kubernetes fixtures.

Acceptance criteria:

- AIRP can list AIRP-client repositories.
- AIRP can list AKS workloads and running images.
- AIRP can map a running pod image to a DockerHub image and likely GitHub repository.

## Phase 6: Kubernetes MCP Integration

Goal: collect reliable, bounded, redacted runtime evidence from Azure AKS.

Tasks:

- [ ] Choose Kubernetes MCP transport and configure settings.
- [ ] Configure read-only AKS identity and namespace allowlist.
- [ ] Implement `list_pods`.
- [ ] Implement `get_pod`.
- [ ] Implement `get_pod_logs`.
- [ ] Implement `list_events`.
- [ ] Implement `get_deployment`.
- [ ] Implement `get_rollout_status`.
- [ ] Implement `list_replicasets`.
- [ ] Implement bounded log windows by line count and time range.
- [ ] Add request timeouts.
- [ ] Add retry policy for transient MCP failures.
- [ ] Redact secrets from logs, environment-like strings, tokens, connection strings, and credentials.
- [ ] Hash and store evidence payloads.
- [ ] Store Kubernetes evidence in `evidence_items`.
- [ ] Add evidence source links where possible.
- [ ] Add runbook for Kubernetes MCP outage.
- [ ] Add fixture-based tests.

Acceptance criteria:

- RCA can fetch pod logs, events, restarts, image IDs, deployment status, and rollout state.
- Evidence stored in AIRP is redacted.
- MCP failures create visible incident events and graceful escalation.

## Phase 7: GitHub MCP Integration

Goal: correlate incidents with AIRP-client repository history and create governed GitHub artifacts.

Tasks:

- [ ] Choose GitHub MCP transport and configure settings.
- [ ] Configure least-privilege org-scoped credentials for AIRP-client.
- [ ] Implement repository listing.
- [ ] Implement repository metadata fetch.
- [ ] Implement branch lookup.
- [ ] Implement commit lookup by SHA.
- [ ] Implement commit lookup by time window.
- [ ] Implement changed-files lookup.
- [ ] Implement merged PR lookup by repository and time window.
- [ ] Implement issue lookup by idempotency marker.
- [ ] Implement issue creation with idempotency.
- [ ] Implement branch creation with safe naming.
- [ ] Implement file read on target branch.
- [ ] Implement file write only on AIRP-created PR branches.
- [ ] Implement draft PR creation with idempotency.
- [ ] Implement PR comment creation.
- [ ] Block merge operations.
- [ ] Block force-push and branch deletion.
- [ ] Block secret file reads where possible.
- [ ] Persist GitHub issues, PRs, comments, branches, and external IDs in `github_artifacts`.
- [ ] Add fixture-based tests.

Acceptance criteria:

- RCA creates one GitHub issue per incident.
- Replayed workflow does not create duplicate issues.
- Remediation creates a draft PR only after approval.

## Phase 8: Slack Integration and Approval UX

Goal: make incident notification and human approval practical for SREs.

Tasks:

- [ ] Configure Slack app credentials through secrets.
- [ ] Implement Slack signing secret verification.
- [ ] Implement incident notification formatting.
- [ ] Implement threaded updates for RCA progress.
- [ ] Implement threaded updates for GitHub issue creation.
- [ ] Implement threaded updates for remediation plans.
- [ ] Implement approval request messages.
- [ ] Implement signed approval payload generation.
- [ ] Add Slack callback endpoint.
- [ ] Validate Slack callback signatures.
- [ ] Validate approval payload hashes.
- [ ] Add approval expiry.
- [ ] Add replay protection.
- [ ] Store channel, message timestamp, thread timestamp, and permalink.
- [ ] Add idempotency for Slack thread creation and updates.
- [ ] Add tests for signing, verification, expiry, and replay rejection.

Acceptance criteria:

- RCA creates a Slack incident thread.
- SRE can approve or reject from Slack.
- Approval payloads cannot be replayed or modified.

## Phase 9: LangGraph and GenAI Hub Agent Layer

Goal: turn the LLM adapter into safe, structured, evidence-backed LangGraph agent intelligence.

Tasks:

- [x] Add `langgraph` dependency and lock compatible versions.
- [x] Create `src/airp/agents/` package.
- [x] Define shared LangGraph state model for incident ID, workflow ID, service context, evidence IDs, hypotheses, remediation plan, documentation report, errors, confidence, and next action.
- [x] Define common agent runtime interfaces.
- [ ] Define graph node base utilities for model calls, tool calls, state updates, evidence citations, and incident timeline events.
- [x] Implement LangGraph supervisor skeleton that routes Monitoring to Embedding.
- [ ] Extend LangGraph supervisor routing to Correlation, RCA, Remediation, and Documentation agents.
- [ ] Add graph checkpoints using PostgreSQL or Redis-backed durable state.
- [ ] Add graph resume behavior after worker restart.
- [ ] Add graph-level idempotency keys for external artifact creation.
- [ ] Add graph-level timeout, retry, and escalation rules.
- [x] Wire Temporal `IncidentWorkflow` activities to invoke the LangGraph supervisor.
- [ ] Emit `airp.agent.events` for every graph node start, success, failure, retry, and decision.
- [ ] Define prompt template loader and versioning.
- [x] Add Monitoring Agent graph node.
- [x] Add Monitoring Agent prompt and structured output.
- [x] Monitoring Agent: classify alert validity, severity, affected service, noisy/duplicate signal risk, and initial routing decision.
- [x] Monitoring Agent: write `monitoring.assessed` incident event.
- [ ] Add Correlation Agent graph node.
- [ ] Add Correlation Agent prompt and structured output.
- [ ] Correlation Agent: fetch service catalog, runtime workload mapping, recent related incidents, and pgvector incident memory.
- [ ] Correlation Agent: produce compact context for RCA and remediation.
- [ ] Add RCA Agent graph node.
- [ ] Add RCA Agent prompt and structured output.
- [ ] RCA Agent: call Kubernetes MCP for pods, logs, events, deployments, rollout state, restart count, image ID, and namespace context.
- [ ] RCA Agent: call GitHub MCP for commits, merged PRs, changed files, releases, owners, and prior issues.
- [ ] RCA Agent: call DockerHub client for image tag and digest correlation.
- [ ] RCA Agent: produce ranked hypotheses with confidence, evidence IDs, contradictions, and next actions.
- [ ] RCA Agent: create exactly one idempotent GitHub issue when policy allows.
- [ ] RCA Agent: send Slack incident notification when policy allows.
- [ ] Add Remediation Agent graph node.
- [ ] Add Remediation Agent prompt and structured output.
- [ ] Remediation Agent: read RCA evidence, GitHub issue, repository context, and service policy.
- [ ] Remediation Agent: generate remediation plan, test plan, rollback plan, risk score, approval requirement, and blocked-file analysis.
- [ ] Remediation Agent: wait for approval signal before repository write actions.
- [ ] Remediation Agent: create branch and draft PR through GitHub MCP after approval only.
- [ ] Add Documentation Agent graph node.
- [ ] Add Documentation Agent prompt and structured output.
- [ ] Documentation Agent: generate final RCA report from timeline, evidence, hypotheses, issue, PR, Slack thread, approval, and outcome.
- [ ] Documentation Agent: store final report and publish to configured wiki target when enabled.
- [x] Add Embedding Agent graph node.
- [x] Add Embedding Agent prompt-free embedding workflow using GenAI Hub `embeddings`.
- [ ] Embedding Agent: generate embeddings for incident symptoms, evidence summaries, RCA hypotheses, remediation outcomes, and final report.
- [x] Embedding Agent: redact secret-like content before embedding.
- [ ] Embedding Agent: persist vectors in PostgreSQL + pgvector once vector migration is complete.
- [ ] Embedding Agent: retry embedding failures without blocking urgent remediation.
- [x] Add typed Pydantic output schemas for Monitoring and Embedding agents.
- [ ] Add typed Pydantic output schemas for Correlation, RCA, Remediation, and Documentation agents.
- [ ] Persist model calls with prompt version, model name, latency, token counts, response hash, validation result, and incident ID.
- [ ] Add model fallback policy by incident severity.
- [ ] Add token and cost estimation.
- [ ] Add rate-limit and timeout escalation behavior.
- [ ] Require evidence citations for RCA and remediation outputs.
- [ ] Reject unsupported claims or low-confidence outputs.
- [ ] Add prompt-injection hardening for Kubernetes logs, GitHub content, Slack text, and user-provided fields.
- [ ] Add structured output validation failures to incident timeline.
- [x] Add LangGraph unit tests for supervisor routing.
- [x] Add LangGraph node tests with mocked GenAI Hub and embedding dependencies.
- [ ] Add LangGraph node tests with mocked Kubernetes MCP, GitHub MCP, Slack, DockerHub, and pgvector dependencies.
- [ ] Add graph replay/resume tests.
- [ ] Add LLM eval fixtures for high latency, crash loop, bad deployment, config error, and missing evidence scenarios.
- [ ] Document GenAI Hub configuration without committing secrets.

Acceptance criteria:

- Temporal workflow invokes the LangGraph supervisor for incident processing.
- Monitoring, RCA, Documentation, Remediation, and Embedding agents are implemented as LangGraph nodes.
- Every agent response validates against a Pydantic schema.
- RCA hypotheses cite stored evidence IDs.
- Embedding Agent stores searchable incident memory without secret-like content.
- Unsupported or low-confidence conclusions escalate instead of remediating.

## Phase 10: Correlation and Incident Memory

Goal: use historical incidents to improve RCA and remediation.

Tasks:

- [ ] Enable pgvector in migrations.
- [ ] Store embeddings for incident symptoms.
- [ ] Store embeddings for RCA summaries.
- [ ] Store embeddings for remediation outcomes.
- [ ] Store embeddings for final documentation reports.
- [ ] Implement vector-backed search.
- [ ] Combine vector score with service match, environment, recency, and remediation success.
- [ ] Update `GET /api/search/incidents` to use semantic search when query text is present.
- [ ] Add background embedding jobs.
- [ ] Add embedding retry behavior.
- [ ] Add tests for ranking behavior.
- [ ] Add safeguards to avoid embedding secret-like content.

Acceptance criteria:

- Similar historical incidents are returned for a new incident.
- Correlation Agent includes prior fixes and outcomes in RCA context.

## Phase 11: RCA Agent End-to-End

Goal: create an evidence-backed RCA and GitHub issue for incidents.

Tasks:

- [ ] Implement RCA workflow activity orchestration.
- [ ] Collect Kubernetes pod logs, events, restarts, image IDs, and deployment state.
- [ ] Collect GitHub commits, PRs, issues, release metadata, and changed files.
- [ ] Correlate AKS image ID to DockerHub digest.
- [ ] Correlate DockerHub digest or tag to GitHub commit.
- [ ] Build RCA evidence bundle.
- [ ] Invoke GenAI Hub with structured RCA schema.
- [ ] Store evidence-backed ranked hypotheses.
- [ ] Create GitHub issue in affected repository.
- [ ] Send Slack notification with issue link.
- [ ] Update incident status to `RCA_ISSUE_CREATED` and `SLACK_NOTIFIED`.
- [ ] Add golden tests for high latency.
- [ ] Add golden tests for crash loop.
- [ ] Add golden tests for bad deployment.
- [ ] Add golden tests for config error.

Acceptance criteria:

- A synthetic incident produces a GitHub issue and Slack thread with cited evidence.
- The issue links back to AIRP and includes affected pod, image, commit, and probable root cause.

## Phase 12: Remediation Agent End-to-End

Goal: create safe, approved remediation plans and draft PRs.

Tasks:

- [ ] Define remediation policy schema.
- [ ] Configure risk levels, max changed files, protected paths, required tests, and approval rules.
- [ ] Generate remediation plan from RCA evidence.
- [ ] Generate rollback plan.
- [ ] Store remediation plan and rollback plan.
- [ ] Request approval through API and Slack.
- [ ] Wait for approval workflow signal.
- [ ] Block PR creation until approval when required.
- [ ] Create branch through GitHub MCP.
- [ ] Generate minimal code or config diff.
- [ ] Validate changed files against policy.
- [ ] Create draft PR with RCA evidence, tests, rollback plan, risk level, and approval record.
- [ ] Link PR to GitHub issue and AIRP incident.
- [ ] Track CI status.
- [ ] Update incident timeline with CI and PR events.
- [ ] Escalate when proposed change exceeds risk policy.

Acceptance criteria:

- Remediation cannot create a PR without required approval.
- Approved remediation creates one linked draft PR.
- PR body contains evidence, test plan, rollback plan, risk, and approval details.

## Phase 13: Documentation Agent and Knowledge Loop

Goal: close incidents with reusable RCA documentation.

Tasks:

- [ ] Define final RCA report schema.
- [ ] Generate report from timeline, evidence, hypotheses, GitHub issue, PR, Slack thread, and outcome.
- [ ] Store final report in PostgreSQL.
- [ ] Publish report to selected wiki target when configured.
- [ ] Add manual republish endpoint.
- [ ] Generate prevention follow-up tasks.
- [ ] Embed final report for search.
- [ ] Add publishing retries and dead-letter behavior.
- [ ] Add tests for report generation and retry behavior.

Acceptance criteria:

- Closed incident has a final RCA report.
- Final report is searchable through incident memory.
- Documentation failure is visible and retryable without blocking urgent remediation.

## Phase 14: API Completion

Goal: expose clean backend APIs for operators and automation clients.

Tasks:

- [ ] Add workflow state endpoint.
- [ ] Add workflow signal endpoints for pause, resume, retry, escalate, close.
- [ ] Add evidence listing endpoint.
- [ ] Add RCA hypothesis listing endpoint.
- [ ] Add GitHub artifact listing endpoint.
- [ ] Add Slack message listing endpoint.
- [ ] Add model call listing endpoint with safe prompt/response redaction.
- [ ] Add tool call listing endpoint.
- [ ] Add audit export endpoint.
- [ ] Add policy management endpoint for Admin users.
- [ ] Add manual discovery refresh endpoint.
- [ ] Add manual documentation republish endpoint.
- [ ] Add OpenAPI examples for all production APIs.

Acceptance criteria:

- Operators can inspect every incident artifact through API.
- Automation clients can signal workflows safely.
- Sensitive model/tool data is redacted by default.

## Phase 15: Observability and Operations

Goal: make AIRP observable, debuggable, and operable.

Tasks:

- [ ] Add OpenTelemetry FastAPI instrumentation.
- [ ] Add OpenTelemetry instrumentation for workers.
- [ ] Add Prometheus metrics endpoint.
- [ ] Track API request count, latency, and errors.
- [ ] Track workflow count, activity latency, and workflow failures.
- [ ] Track alert consumer processed, duplicate, dead-letter, and failure counts.
- [ ] Track agent latency, model tokens, model failures, and fallback count.
- [ ] Track MCP call latency and failure count.
- [ ] Track approval latency.
- [ ] Add structured logging with incident ID, workflow ID, request ID, and correlation ID.
- [ ] Add dependency health checks for PostgreSQL, Redis, Temporal, Event Hubs, GenAI Hub, Kubernetes MCP, GitHub MCP, DockerHub, and Slack.
- [ ] Add readiness behavior that fails when required dependencies are unavailable.
- [ ] Add Grafana dashboard JSON or provisioning docs.
- [ ] Add runbooks for dependency failures.

Acceptance criteria:

- Operators can identify dependency failures from health and metrics.
- Every incident workflow has correlated logs and metrics.

## Phase 16: Security Hardening

Goal: satisfy production security expectations for an autonomous remediation system.

Tasks:

- [ ] Add secret scanning to CI.
- [ ] Add dependency vulnerability scanning.
- [ ] Add container image scanning.
- [ ] Add SBOM generation.
- [ ] Add request body size limits.
- [ ] Add rate limiting for public and protected endpoints.
- [ ] Add strict production CORS allowlist.
- [ ] Add response security headers.
- [ ] Add audit trail coverage checks.
- [ ] Add secret-like content detection before LLM prompts, logs, issues, Slack messages, PRs, and embeddings.
- [ ] Add MCP parameter hashing for sensitive tool calls.
- [ ] Add allowlist for GitHub repositories under AIRP-client.
- [ ] Add namespace allowlist for Kubernetes evidence collection.
- [ ] Add blocked file/path policy for remediation.
- [ ] Add branch protection and required-checks documentation for AIRP-client repos.
- [ ] Add key rotation runbooks.

Acceptance criteria:

- Secrets are blocked or redacted before leaving AIRP.
- Security scans run in CI.
- Audit trail can reconstruct every model call, tool call, approval, and repository write.

## Phase 17: CI/CD and Release Automation

Goal: make releases repeatable and safe.

Tasks:

- [ ] Add GitHub Actions workflow for lint and tests.
- [ ] Add PostgreSQL migration test job.
- [ ] Add Docker build workflow.
- [ ] Add container scan workflow.
- [ ] Add SBOM workflow.
- [ ] Add Helm lint and template checks.
- [ ] Publish AIRP backend image to approved registry.
- [ ] Add tagged release workflow.
- [ ] Add changelog generation.
- [ ] Add deployment workflow to AKS.
- [ ] Add migration execution step for deployment.
- [ ] Add rollback workflow.
- [ ] Add environment-specific Helm values files.

Acceptance criteria:

- Main branch cannot merge unless lint, tests, migration checks, image build, and Helm checks pass.
- Tagged release builds and publishes an image.
- AKS deployment can be rolled back.

## Phase 18: Azure AKS Production Deployment

Goal: run AIRP in the target Azure environment.

Tasks:

- [ ] Provision production PostgreSQL with pgvector.
- [ ] Provision production Redis.
- [ ] Provision Temporal service or cluster.
- [ ] Provision Event Hubs namespace and topics.
- [ ] Configure Event Hubs Kafka credentials through Kubernetes secrets.
- [ ] Configure GenAI Hub key through Kubernetes secrets.
- [ ] Configure GitHub MCP credentials through Kubernetes secrets.
- [ ] Configure Slack credentials through Kubernetes secrets.
- [ ] Configure Kubernetes MCP access to AKS.
- [ ] Deploy AIRP API with at least two replicas.
- [ ] Deploy alert consumer worker.
- [ ] Deploy Temporal worker.
- [ ] Configure ingress, TLS, DNS, and network policy.
- [ ] Configure workload identity where possible.
- [ ] Verify health, readiness, protected APIs, Event Hubs consumer, and Temporal worker.
- [ ] Validate logs and metrics in the target observability stack.

Acceptance criteria:

- AIRP API runs in AKS with production auth enabled.
- Workers run and connect to Temporal/Event Hubs.
- Secrets are not stored in plain Helm values.

## Phase 19: End-to-End Incident Simulations

Goal: prove the complete product with realistic incidents.

Tasks:

- [ ] Create synthetic Alertmanager payload for high latency.
- [ ] Create synthetic Alertmanager payload for crash loop.
- [ ] Create synthetic Alertmanager payload for bad config.
- [ ] Create synthetic Alertmanager payload for failed deployment.
- [ ] Create controlled test repo in AIRP-client.
- [ ] Ensure test repo builds public DockerHub image.
- [ ] Deploy test image to AKS.
- [ ] Trigger alert into Event Hubs.
- [ ] Verify incident creation.
- [ ] Verify Temporal workflow start.
- [ ] Verify Kubernetes evidence collection.
- [ ] Verify DockerHub image correlation.
- [ ] Verify GitHub commit and PR correlation.
- [ ] Verify structured GenAI RCA.
- [ ] Verify GitHub issue creation.
- [ ] Verify Slack notification.
- [ ] Verify approval request.
- [ ] Verify approved draft PR creation.
- [ ] Verify final documentation report.
- [ ] Verify incident embedding and search.
- [ ] Verify replay does not create duplicate incident, issue, Slack thread, or PR.
- [ ] Record demo script and troubleshooting notes.

Acceptance criteria:

- A real alert completes the path from detection to issue, notification, approval, PR, and RCA documentation.
- Replay remains idempotent across all external artifacts.

## Phase 20: Load, Resilience, and Chaos Testing

Goal: prove AIRP behaves under production stress and dependency failures.

Tasks:

- [ ] Load test alert ingestion bursts.
- [ ] Load test API read paths.
- [ ] Load test concurrent incidents across multiple services.
- [ ] Simulate Event Hubs outage.
- [ ] Simulate Temporal outage and worker restart.
- [ ] Simulate Redis outage.
- [ ] Simulate PostgreSQL restart.
- [ ] Simulate GenAI Hub timeout and rate limit.
- [ ] Simulate Kubernetes MCP outage.
- [ ] Simulate GitHub MCP outage.
- [ ] Simulate DockerHub outage.
- [ ] Simulate Slack outage.
- [ ] Verify retry behavior.
- [ ] Verify dead-letter behavior.
- [ ] Verify escalation behavior.
- [ ] Verify no duplicate external artifacts during retries.

Acceptance criteria:

- Failures leave visible audit trail and actionable escalation.
- Retried workflows do not duplicate GitHub issues, Slack messages, or PRs.

## Phase 21: Documentation and Handoff

Goal: make AIRP operable by another engineer or SRE team.

Tasks:

- [ ] Complete architecture documentation.
- [ ] Complete backend API reference.
- [ ] Complete authentication and authorization guide.
- [ ] Complete PostgreSQL and pgvector setup guide.
- [ ] Complete Event Hubs setup guide.
- [ ] Complete Temporal setup guide.
- [ ] Complete Kubernetes MCP setup guide.
- [ ] Complete GitHub MCP setup guide.
- [ ] Complete Slack app setup guide.
- [ ] Complete GenAI Hub configuration guide.
- [ ] Complete AKS deployment guide with environment-specific values.
- [ ] Complete runbook for incident replay.
- [ ] Complete runbook for approval issues.
- [ ] Complete runbook for key rotation.
- [ ] Complete runbook for worker outage.
- [ ] Complete runbook for dependency outage.
- [ ] Complete rollback guide.
- [ ] Add onboarding guide for a new AIRP-client service.
- [ ] Add production readiness checklist.

Acceptance criteria:

- A new engineer can deploy AIRP from the docs.
- A new AIRP-client service can be onboarded without code changes.

## Cross-Cutting Backlog

- [ ] Add typed domain events for every state transition.
- [ ] Add event schema versioning and compatibility checks.
- [ ] Add shared idempotency key helper library.
- [ ] Add centralized policy engine for approval and remediation guardrails.
- [ ] Add feature flags for issue creation, Slack notification, PR creation, and documentation publishing.
- [ ] Add tenant/environment separation if more client environments are added.
- [ ] Add database backup and restore scripts.
- [ ] Add cleanup jobs for stale Redis keys, old dead letters, and old workflow artifacts.
- [ ] Add admin API for model routing and policy configuration.
- [ ] Add cost dashboard for GenAI Hub usage.
- [ ] Add data retention policy for prompts, logs, evidence, and audit records.
- [ ] Add legal/compliance review checklist for autonomous remediation behavior.
- [ ] Add LangGraph graph versioning and migration policy.
- [ ] Add graph execution trace export for audit/debugging.

## Immediate Next Sprint

Sprint goal: expand LangGraph beyond Monitoring and Embedding into Correlation and RCA evidence planning.

Tasks:

1. Add Correlation Agent state and structured output schema.
2. Add Correlation Agent graph node.
3. Fetch service catalog and runtime workload context for an incident.
4. Add fixture-backed repository/workload correlation tests.
5. Add RCA Agent state and structured output schema.
6. Add RCA Agent graph node skeleton.
7. Collect currently available incident evidence and monitoring output into an RCA evidence bundle.
8. Extend supervisor routing from Monitoring -> Correlation -> RCA -> Embedding.
9. Persist `correlation.completed` and `rca.started` timeline events.
10. Add tests for supervisor routing through Correlation and RCA.

Demo at end of sprint:

```text
sample alert -> Event Hubs raw topic -> alert consumer -> incident row -> Temporal workflow -> LangGraph supervisor -> Monitoring Agent -> Correlation Agent -> RCA Agent -> timeline events -> API lookup
```

## Production-Ready Definition

AIRP is production-ready only when all of the following are true:

- Real AKS incident evidence is collected through Kubernetes MCP.
- Real AIRP-client repository evidence is collected through GitHub MCP.
- AIRP can map AKS running images to DockerHub images and likely GitHub repositories.
- LangGraph supervisor orchestrates Monitoring, Correlation, RCA, Remediation, Documentation, and Embedding agents.
- GenAI Hub agent outputs are structured, validated, redacted, and evidence-backed.
- RCA creates one idempotent GitHub issue per incident.
- Slack incident notification and approval flow works.
- Remediation creates approved draft PRs with policy guardrails.
- Documentation Agent creates final RCA reports and embeddings.
- PostgreSQL + pgvector incident memory is active.
- Temporal workflows survive worker restarts and retries.
- Event Hubs replay does not create duplicate artifacts.
- Secrets are managed through Kubernetes secrets or an external secret manager.
- CI runs lint, tests, migration checks, image build, scan, and Helm checks.
- AKS deployment has monitoring, alerts, runbooks, rollback, and audit export.

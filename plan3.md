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
- LangGraph dependency, `src/airp/agents/` package, supervisor skeleton, Monitoring Agent node, Correlation Agent node, RCA Agent skeleton, Embedding Agent node, and Temporal `agent_graph_run` activity hook.
- Read-only RCA evidence DTOs and fixture-backed adapters for Kubernetes MCP, GitHub MCP, and DockerHub.
- RCA Agent evidence collector boundary that records planned/completed/unavailable tool calls without mutating external systems.
- RCA evidence bundle sections for Kubernetes, GitHub, DockerHub, and tool calls.
- Temporal `agent_graph_run` persistence for RCA Kubernetes/GitHub/DockerHub evidence items and recorded tool calls.
- RCA hypothesis Pydantic schemas, versioned RCA prompt, structured GenAI Hub hypothesis path, and deterministic low-evidence escalation fallback.
- Temporal `agent_graph_run` persistence for RCA hypotheses and GenAI model-call audit records.
- RCA safety hardening for unsupported claims, low-confidence escalation, prompt-injection text in evidence, and scenario fixtures.
- Read APIs for incident evidence, tool calls, model calls, and RCA hypotheses.
- Disabled-by-default external action policy flags and shared artifact idempotency helper for future GitHub, Slack, PR, and documentation writes.
- Live-read configuration scaffolding for Kubernetes MCP, GitHub MCP, and DockerHub, including endpoint settings, read timeouts, retry settings, namespace/repository allowlists, readiness checks, and failure timeline events.
- Dockerfile, Docker Compose, Helm chart, AKS helper script, migration script, deployment docs, and verification script.
- Helm deployment defaults expose the read-only evidence configuration and use `/api/readiness` for API readiness probing.
- Unit and smoke tests for the implemented foundation.

Still not production complete:

- Full Temporal workflow execution is not complete beyond the MVP workflow skeleton.
- LangGraph supervisor MVP is implemented through Monitoring, Correlation, RCA evidence planning, RCA hypotheses, and Embedding, but Remediation and Documentation agents remain pending.
- Live Kubernetes MCP, live GitHub MCP, Slack, approval UX, and governed repository-write behavior are not end-to-end.
- PostgreSQL + pgvector has not been fully verified with migrations and integration tests.
- Entra ID authorization roles are not production-grade yet.
- Observability, security hardening, CI/CD, and AKS production deployment need to be finished.

## Verified Agent-Orchestration Status

Verified from the current repository on 2026-05-16:

- `langgraph` is listed in `pyproject.toml`.
- `src/airp/agents/` exists.
- Monitoring Agent is implemented as a LangGraph node with structured output validation.
- Embedding Agent is implemented as a LangGraph node with redaction before embedding calls.
- Correlation and RCA Agent skeletons are implemented as LangGraph nodes.
- Documentation and Remediation agents are not implemented as LangGraph nodes yet.
- RCA Agent can use a configured read-only evidence collector for Kubernetes MCP, GitHub MCP, and DockerHub evidence.
- RCA Agent generates typed RCA hypotheses with confidence, evidence refs, contradictions, next actions, and escalation decision.
- RCA Agent rejects unsupported or uncited model claims, escalates low-confidence output, and sanitizes untrusted evidence before prompt construction.
- RCA Agent records model-call audit metadata for structured GenAI Hub hypothesis generation.
- Kubernetes, GitHub, and DockerHub evidence clients support fixture-backed reads and typed DTOs for deterministic tests.
- Kubernetes MCP and GitHub MCP clients now carry live-read transport settings, endpoint URLs, and read timeouts, while live transport methods remain pending.
- DockerHub client supports live public tag/digest lookup with configurable timeout and HTTP transport mocking.
- RCA evidence collection enforces configured Kubernetes namespace and GitHub repository allowlists before making read calls.
- RCA evidence collection records unavailable, forbidden, and timeout outcomes as visible incident timeline events.
- RCA evidence persistence stores evidence item payload hashes and tool-call parameter/result hashes.
- Current Temporal workflow invokes a LangGraph supervisor through the `agent_graph_run` activity.
- Current GenAI Hub integration is used as an optional LLM/embedding adapter; RCA prompt/model-call persistence is implemented, while broader production prompt templates are still pending.

## Remaining Work Summary

The remaining product work is:

- PostgreSQL/pgvector migration verification and production-grade repository/query layer.
- Microsoft Entra ID issuer discovery, JWKS caching, app roles, and route-level authorization.
- Live Azure Event Hubs validation, consumer metrics, and replay/dead-letter operations.
- Temporal workflow hardening: full lifecycle states, retries, workflow replay tests, restart tests, evidence/approval/documentation queries, and external-artifact idempotency.
- AIRP-client discovery: GitHub repositories, DockerHub public image metadata, AKS workload inventory, and repository-to-image-to-workload mapping.
- Kubernetes MCP implementation for pod logs, events, deployments, rollout state, replica sets, redaction, and evidence storage.
- GitHub MCP implementation for repository history, issues, branches, file writes through PR branches, draft PRs, comments, and artifact persistence.
- Slack notification, signed approval callbacks, threaded updates, replay protection, and approval expiry.
- LangGraph expansion from the current Monitoring, Correlation, RCA evidence/hypothesis, and Embedding MVP into live RCA evidence collection, Remediation, Documentation, graph checkpoints, graph resume, and graph execution audit.
- GenAI Hub production agent controls beyond the RCA prompt: shared prompt loading, model fallback policy, token/cost tracking, groundedness rules, prompt-injection hardening, and eval fixtures.
- Incident memory: pgvector-backed embeddings, semantic search, background embedding jobs, ranking tests, and secret-safe embedding policy.
- End-to-end RCA, remediation, documentation, and knowledge-loop behavior.
- API completion for GitHub artifacts, Slack messages, audit export, policy management, refresh, and republish flows.
- Observability, security hardening, CI/CD, AKS production deployment, end-to-end simulations, resilience testing, and handoff documentation.

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
2. Finish Temporal workflow hardening beyond the current MVP.
3. Finish live Event Hubs and PostgreSQL validation.
4. Finish live discovery and evidence collection through Kubernetes MCP, GitHub MCP, and DockerHub.
5. Expand LangGraph-based structured GenAI agents beyond Monitoring, Correlation, RCA, and Embedding.
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

- [x] Add Microsoft Entra ID JWT validator boundary.
- [x] Validate configured Entra `aud`, `iss`, `exp`, and `iat` claims.
- [x] Extract principal subject, tenant, username, roles, and scopes.
- [x] Add reusable role-check dependency helper.
- [ ] Add issuer discovery from Entra `/.well-known/openid-configuration`.
- [ ] Cache JWKS and refresh on key rotation.
- [ ] Validate `nbf`, required `tid`, and required app roles.
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
- [x] Package alert consumer as a separate Kubernetes Deployment.
- [x] Add Helm template support for API, alert consumer, and Temporal worker deployments.
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
- [x] Add basic workflow states for received, validated, agent graph completed, paused, approved, rejected, escalated, and closed.
- [x] Add workflow states/events for RCA hypotheses generated, issue creation skipped, and Slack notification skipped.
- [ ] Add workflow states for correlation, issue creation created, Slack notification sent, remediation planning, approval wait, PR creation, documentation, closure, and escalation.
- [x] Implement workflow activities for database state updates.
- [x] Implement workflow activity hook for LangGraph Monitoring, Correlation, RCA planning, and Embedding.
- [x] Persist RCA Kubernetes/GitHub/DockerHub evidence sections and recorded tool calls from `agent_graph_run`.
- [x] Persist RCA hypotheses and RCA model-call audit records from `agent_graph_run`.
- [ ] Implement dedicated live workflow activities for Kubernetes evidence, GitHub evidence, DockerHub image evidence, GitHub issue creation, Slack notifications, remediation planning, approval handling, PR creation, documentation, and closure.
- [x] Add workflow signals: pause, resume, approve, reject, escalate, close.
- [ ] Add workflow signal for retry failed activity.
- [x] Add workflow query for current state and current step.
- [ ] Add workflow queries for evidence summary, approval request, and timeline.
- [ ] Add idempotency keys for every activity that writes external artifacts.
- [x] Add basic activity retry policy with backoff for current Temporal activities.
- [x] Add start-to-close activity timeouts for current Temporal activities.
- [x] Add dedicated retry settings for the current agent graph activity that includes RCA hypothesis generation and evidence persistence.
- [ ] Add activity-specific retry policies with non-retryable error types for each external integration.
- [ ] Add heartbeat handling for long evidence collection.
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
- [x] Define DockerHub image evidence DTOs for image, repository, tag, digest, source commit, and raw metadata.
- [x] Add Docker image reference parser for registry, tag, and digest formats.
- [x] Add fixture-backed DockerHub image metadata lookup for RCA Agent tests.
- [ ] Implement DockerHub public image tag listing.
- [x] Implement DockerHub digest lookup for image tags.
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

- [x] Define Kubernetes evidence DTOs for pods, logs, events, deployments, rollout status, and replica sets.
- [x] Add fixture-backed Kubernetes MCP read methods for RCA Agent tests and offline workflow development.
- [x] Add Kubernetes evidence redaction through the RCA evidence collector before storage.
- [x] Store Kubernetes RCA evidence sections in `evidence_items` when collected by the RCA Agent.
- [x] Add fixture-based Kubernetes evidence client tests.
- [x] Add Kubernetes MCP transport, endpoint URL, namespace allowlist, and read timeout settings.
- [ ] Configure read-only AKS identity for the Kubernetes MCP server.
- [ ] Implement live `list_pods` through selected MCP transport.
- [ ] Implement live `get_pod` through selected MCP transport.
- [ ] Implement live `get_pod_logs` through selected MCP transport.
- [ ] Implement live `list_events` through selected MCP transport.
- [ ] Implement live `get_deployment` through selected MCP transport.
- [ ] Implement live `get_rollout_status` through selected MCP transport.
- [ ] Implement live `list_replicasets` through selected MCP transport.
- [ ] Implement bounded log windows by line count and time range.
- [x] Add request timeout settings.
- [x] Add retry policy for transient MCP failures.
- [ ] Redact secrets from logs, environment-like strings, tokens, connection strings, and credentials.
- [ ] Hash and store evidence payloads.
- [ ] Store Kubernetes evidence in `evidence_items`.
- [ ] Add evidence source links where possible.
- [ ] Add runbook for Kubernetes MCP outage.

Acceptance criteria:

- RCA can fetch pod logs, events, restarts, image IDs, deployment status, and rollout state.
- Evidence stored in AIRP is redacted.
- MCP failures create visible incident events and graceful escalation.

## Phase 7: GitHub MCP Integration

Goal: correlate incidents with AIRP-client repository history and create governed GitHub artifacts.

Tasks:

- [x] Define GitHub evidence DTOs for commits, merged PRs, changed files, releases, and prior issues.
- [x] Add fixture-backed GitHub MCP read methods for repository evidence used by RCA Agent tests.
- [x] Keep GitHub issue and PR creation disabled until approval and policy gates are implemented.
- [x] Store GitHub RCA evidence sections in `evidence_items` when collected by the RCA Agent.
- [x] Add fixture-based GitHub MCP evidence tests.
- [x] Add GitHub MCP transport, endpoint URL, AIRP-client repository allowlist, and read timeout settings.
- [ ] Configure least-privilege org-scoped credentials for AIRP-client.
- [x] Add retry policy for transient GitHub MCP read failures.
- [ ] Implement live repository listing.
- [ ] Implement live repository metadata fetch.
- [ ] Implement live branch lookup.
- [ ] Implement live commit lookup by SHA.
- [ ] Implement live commit lookup by time window.
- [ ] Implement live changed-files lookup.
- [ ] Implement live merged PR lookup by repository and time window.
- [ ] Implement live issue lookup by idempotency marker.
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
- [x] Add read-only RCA tool-call recording boundary for Kubernetes MCP, GitHub MCP, and DockerHub.
- [x] Implement LangGraph supervisor skeleton that routes Monitoring to Embedding.
- [x] Extend LangGraph supervisor routing to Correlation and RCA agents.
- [ ] Extend LangGraph supervisor routing to Remediation and Documentation agents.
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
- [x] Add Correlation Agent graph node.
- [ ] Add Correlation Agent prompt.
- [x] Add Correlation Agent structured output.
- [x] Correlation Agent: fetch service catalog and runtime workload mapping.
- [ ] Correlation Agent: fetch recent related incidents and pgvector incident memory.
- [x] Correlation Agent: produce compact context for RCA and remediation.
- [x] Add RCA Agent graph node.
- [x] Add RCA Agent prompt.
- [x] Add versioned RCA prompt template.
- [x] Add RCA Agent structured output.
- [x] RCA Agent: call configured read-only evidence collector for Kubernetes, GitHub, and DockerHub evidence.
- [ ] RCA Agent: call live Kubernetes MCP for pods, logs, events, deployments, rollout state, restart count, image ID, and namespace context.
- [ ] RCA Agent: call live GitHub MCP for commits, merged PRs, changed files, releases, owners, and prior issues.
- [x] RCA Agent: call live DockerHub client for image tag and digest correlation.
- [x] RCA Agent: build initial evidence-planning bundle from incident, monitoring, catalog, and workload context.
- [x] RCA Agent: extend evidence bundle with Kubernetes, GitHub, and DockerHub evidence.
- [x] RCA Agent: produce ranked hypotheses with confidence, evidence IDs, contradictions, and next actions.
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
- [x] Embedding Agent: generate embeddings for incident symptoms and current graph summaries when an embedding client is configured.
- [ ] Embedding Agent: generate embeddings for stored evidence summaries, RCA hypotheses, remediation outcomes, and final report.
- [x] Embedding Agent: redact secret-like content before embedding.
- [ ] Embedding Agent: persist vectors in PostgreSQL + pgvector once vector migration is complete.
- [ ] Embedding Agent: retry embedding failures without blocking urgent remediation.
- [x] Add typed Pydantic output schemas for Monitoring and Embedding agents.
- [x] Add typed Pydantic output schemas for Correlation and RCA agents.
- [ ] Add typed Pydantic output schemas for Remediation and Documentation agents.
- [x] Persist RCA model calls with prompt version, model name, latency, response hash, validation result, and incident ID.
- [ ] Persist token counts for model calls when gateway usage metadata is available.
- [ ] Add model fallback policy by incident severity.
- [ ] Add token and cost estimation.
- [ ] Add rate-limit and timeout escalation behavior.
- [x] Require RCA hypothesis evidence refs and persist stored evidence ID links when evidence items are stored.
- [ ] Require evidence citations for remediation outputs.
- [x] Add deterministic low-evidence escalation fallback for RCA hypotheses.
- [x] Reject unsupported RCA claims from model output.
- [x] Add RCA prompt-injection hardening for Kubernetes logs and GitHub content.
- [ ] Add prompt-injection hardening for Slack text and remaining user-provided fields.
- [ ] Add structured output validation failures to incident timeline.
- [x] Add LangGraph unit tests for supervisor routing.
- [x] Add LangGraph node tests with mocked GenAI Hub and embedding dependencies.
- [x] Add LangGraph node tests with fixture-backed service/workload correlation.
- [x] Add LangGraph RCA node tests with mocked Kubernetes MCP, GitHub MCP, and DockerHub dependencies.
- [ ] Add LangGraph node tests with mocked Slack and pgvector dependencies.
- [ ] Add graph replay/resume tests.
- [x] Add RCA golden fixtures for high latency, crash loop, bad deployment, config error, and failed deployment scenarios.
- [ ] Add LLM eval fixtures for missing evidence and model timeout scenarios.
- [ ] Document GenAI Hub configuration without committing secrets.

Acceptance criteria:

- Temporal workflow invokes the LangGraph supervisor for incident processing.
- Monitoring, Correlation, RCA, Documentation, Remediation, and Embedding agents are implemented as LangGraph nodes.
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

- [x] Implement RCA graph-node skeleton and initial evidence-planning bundle.
- [x] Add read-only RCA evidence collector boundary for Kubernetes MCP, GitHub MCP, and DockerHub.
- [x] Record intended and completed RCA tool calls without enabling external writes.
- [ ] Implement full RCA workflow activity orchestration with Kubernetes, GitHub, DockerHub, Slack, and issue creation steps.
- [x] Collect fixture-backed Kubernetes pod logs, events, restarts, image IDs, and deployment state.
- [ ] Collect Kubernetes pod logs, events, restarts, image IDs, and deployment state.
- [x] Collect fixture-backed GitHub commits, PRs, issues, release metadata, and changed files.
- [ ] Collect GitHub commits, PRs, issues, release metadata, and changed files.
- [x] Collect fixture-backed DockerHub image tag, digest, and source metadata.
- [ ] Correlate AKS image ID to DockerHub digest.
- [ ] Correlate DockerHub digest or tag to GitHub commit.
- [x] Build initial RCA evidence bundle from incident, monitoring, catalog, and workload context.
- [x] Extend RCA evidence bundle with Kubernetes, GitHub, DockerHub, and tool-call sections.
- [ ] Build full RCA evidence bundle with live Kubernetes, GitHub, DockerHub, historical incidents, and stored evidence IDs.
- [x] Invoke GenAI Hub with structured RCA schema when configured.
- [x] Store evidence-backed ranked hypotheses.
- [ ] Create GitHub issue in affected repository.
- [ ] Send Slack notification with issue link.
- [ ] Update incident status to `RCA_ISSUE_CREATED` and `SLACK_NOTIFIED`.
- [x] Add golden tests for high latency.
- [x] Add golden tests for crash loop.
- [x] Add golden tests for bad deployment.
- [x] Add golden tests for config error.
- [x] Add golden tests for failed deployment.

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
- [x] Add workflow signal endpoint for pause, resume, approve, reject, escalate, and close.
- [ ] Add workflow signal endpoint for retry failed activity.
- [x] Add evidence listing endpoint.
- [x] Add RCA hypothesis listing endpoint.
- [x] Add readiness endpoint for Kubernetes MCP, GitHub MCP, and DockerHub configuration.
- [ ] Add GitHub artifact listing endpoint.
- [ ] Add Slack message listing endpoint.
- [x] Add model call listing endpoint with safe prompt/response hashes only.
- [x] Add tool call listing endpoint.
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
- [x] Add readiness configuration checks for Kubernetes MCP, GitHub MCP, and DockerHub.
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
- [x] Add redaction before GenAI Hub chat and embedding requests.
- [x] Add redaction before RCA Kubernetes/GitHub/DockerHub evidence storage.
- [ ] Add secret-like content detection before LLM prompts, logs, issues, Slack messages, PRs, and embeddings.
- [x] Add MCP parameter and result hashing for recorded RCA tool calls.
- [x] Add allowlist for GitHub repositories under AIRP-client.
- [x] Add namespace allowlist for Kubernetes evidence collection.
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
- [x] Add shared idempotency key helper library.
- [ ] Add centralized policy engine for approval and remediation guardrails.
- [x] Add disabled-by-default feature flags for issue creation, Slack notification, PR creation, and documentation publishing.
- [ ] Add tenant/environment separation if more client environments are added.
- [ ] Add database backup and restore scripts.
- [ ] Add cleanup jobs for stale Redis keys, old dead letters, and old workflow artifacts.
- [ ] Add admin API for model routing and policy configuration.
- [ ] Add cost dashboard for GenAI Hub usage.
- [ ] Add data retention policy for prompts, logs, evidence, and audit records.
- [ ] Add legal/compliance review checklist for autonomous remediation behavior.
- [ ] Add LangGraph graph versioning and migration policy.
- [ ] Add graph execution trace export for audit/debugging.

## Remaining Implementation Backlog

Highest-priority remaining engineering tasks:

- [ ] Run all migrations, including incident idempotency and workflow ID migrations, against real PostgreSQL 16.
- [ ] Add pgvector extension migration and convert incident embedding storage from JSON to vector.
- [ ] Add Entra ID issuer discovery, JWKS caching, role validation, and route-level authorization.
- [ ] Validate Event Hubs alert consumer and sample publisher against the real Azure Event Hubs Kafka endpoint.
- [x] Add API readiness behavior for Kubernetes MCP, GitHub MCP, and DockerHub configuration.
- [ ] Add metrics and full health/readiness behavior for API, alert consumer, and Temporal worker.
- [ ] Add Temporal replay tests and worker restart tests.
- [ ] Add graph checkpoints and resume behavior for LangGraph supervisor state.
- [x] Add Kubernetes MCP read DTOs and fixture-backed methods used by RCA Agent.
- [x] Add Kubernetes MCP live-read transport settings, namespace allowlist, read timeout, and retry scaffolding.
- [ ] Add live Kubernetes MCP transport methods used by RCA Agent.
- [x] Add GitHub MCP read DTOs and fixture-backed methods used by RCA Agent.
- [x] Add GitHub MCP live-read transport settings, AIRP-client repository allowlist, read timeout, and retry scaffolding.
- [ ] Add live GitHub MCP transport methods used by RCA Agent.
- [x] Add DockerHub image evidence DTOs and fixture-backed digest/source metadata lookup.
- [x] Add DockerHub live tag/digest lookup with HTTP mock tests and timeout configuration.
- [ ] Add live DockerHub digest/source correlation behavior.
- [x] Persist Kubernetes, GitHub, and DockerHub evidence items from RCA runs.
- [x] Add structured GenAI RCA hypothesis generation with evidence citations.
- [x] Persist RCA hypotheses and RCA model-call audit records.
- [x] Add API endpoints for evidence, RCA hypotheses, tool calls, and model calls.
- [x] Add RCA golden fixtures and safety tests for unsupported claims, low-confidence output, and prompt-injection text.
- [x] Add disabled-by-default external action policy flags and shared idempotency helper.
- [ ] Add idempotent GitHub issue creation after RCA policy allows it.
- [ ] Add Slack notification, signed approval callback, replay protection, and threaded updates.
- [ ] Add Remediation Agent graph node, policy guardrails, approval wait, branch creation, and draft PR creation.
- [ ] Add Documentation Agent graph node, final RCA report storage, publishing, and embedding.
- [ ] Add vector-backed semantic search and ranking tests.
- [ ] Add API endpoints for GitHub artifacts, Slack messages, audit export, policy management, discovery refresh, and report republish.
- [ ] Add CI/CD workflows for lint, tests, migrations, Docker build, image scanning, SBOM, Helm checks, release, deployment, and rollback.
- [ ] Deploy and validate AIRP API, alert consumer, and Temporal worker on Azure AKS with Kubernetes secrets and production auth.
- [ ] Run end-to-end simulations for latency, crash loop, bad config, and failed deployment incidents.
- [ ] Complete production runbooks and handoff documentation.

## Completed Sprint: Read-Only RCA Evidence Boundary

Sprint goal: connect the RCA Agent skeleton to read-only Kubernetes, GitHub, and DockerHub evidence adapters.

Tasks:

1. [x] Define Kubernetes evidence DTOs for pod, logs, events, deployment, rollout status, and replica sets.
2. [x] Implement fixture-backed Kubernetes MCP methods used by RCA Agent.
3. [x] Define GitHub evidence DTOs for commits, merged PRs, changed files, releases, and prior issues.
4. [x] Implement fixture-backed GitHub MCP read methods used by RCA Agent.
5. [x] Define DockerHub image evidence DTOs for image, tag, digest, and source metadata.
6. [x] Extend RCA Agent evidence bundle to include Kubernetes, GitHub, and DockerHub sections.
7. [x] Add RCA Agent tool-call boundary that records intended MCP/DockerHub calls without mutating external systems.
8. [x] Persist Kubernetes/GitHub/DockerHub evidence items from RCA Agent.
9. [x] Update supervisor tests with mocked Kubernetes MCP, GitHub MCP, and DockerHub dependencies.
10. [x] Keep repository writes, GitHub issue creation, Slack notification, and remediation PR creation disabled until approval/policy layers are implemented.

Demo at end of sprint:

```text
sample alert -> Event Hubs raw topic -> alert consumer -> incident row -> Temporal workflow -> LangGraph supervisor -> Monitoring Agent -> Correlation Agent -> RCA Agent -> Kubernetes/GitHub/DockerHub evidence bundle -> timeline events -> API lookup
```

Verification:

- `./scripts/verify.sh` passes with 27 tests.

## Completed Sprint: Structured RCA Hypotheses and Artifact APIs

Sprint goal: turn collected RCA evidence into structured, cited RCA hypotheses and make the evidence/tool-call artifacts inspectable through APIs.

Tasks:

1. [x] Define typed RCA hypothesis Pydantic schemas with rank, confidence, supporting evidence IDs, contradictions, next actions, and escalation decision.
2. [x] Add RCA Agent prompt template and versioning for GenAI Hub structured hypothesis generation.
3. [x] Persist GenAI model calls with model name, prompt version, latency, response hash, and validation result.
4. [x] Persist RCA hypotheses in `rca_hypotheses` with evidence citations.
5. [x] Link stored evidence item IDs back into the RCA evidence bundle after persistence.
6. [x] Add `GET /api/incidents/{incident_id}/evidence` list endpoint.
7. [x] Add `GET /api/incidents/{incident_id}/tool-calls` list endpoint with safe parameter/result hash output.
8. [x] Add `GET /api/incidents/{incident_id}/hypotheses` list endpoint.
9. [x] Add RCA tests for structured GenAI output, missing evidence, and low-confidence escalation fallback.
10. [x] Keep GitHub issue creation, Slack notification, remediation PR creation, and documentation publishing disabled until policy and approval layers are implemented.

Verification:

- `./scripts/verify.sh` passes with 28 tests.

## Completed Sprint: RCA Safety and Write-Policy Scaffolding

Sprint goal: harden RCA hypotheses with scenario fixtures and prepare governed external artifact creation without enabling writes by default.

Tasks:

1. [x] Add golden RCA fixtures for high latency, crash loop, bad deployment, config error, and failed deployment scenarios.
2. [x] Add low-confidence and unsupported-claim rejection tests for RCA hypothesis output.
3. [x] Add prompt-injection hardening tests for Kubernetes logs and GitHub text.
4. [x] Add model-call listing endpoint with safe redaction and hashes only.
5. [x] Add idempotency helper for future GitHub issue, Slack thread, and PR artifact creation.
6. [x] Define GitHub issue creation policy and feature flag, default disabled.
7. [x] Define Slack notification policy and feature flag, default disabled.
8. [x] Add workflow states for RCA hypotheses generated, issue creation skipped, and Slack notification skipped.
9. [x] Add Temporal activity retry settings for RCA hypothesis generation and evidence persistence.
10. [x] Keep repository writes, Slack sends, and documentation publishing disabled until approval/policy layers are implemented.

Verification:

- `./scripts/verify.sh` passes with 40 tests.

## Completed Sprint: Live-Read Configuration and Allowlists

Sprint goal: implement live read-transport configuration and allowlists for Kubernetes MCP, GitHub MCP, and DockerHub without enabling writes.

Tasks:

1. [x] Add Kubernetes MCP transport settings, namespace allowlist settings, and read timeout settings.
2. [x] Add GitHub MCP transport settings, AIRP-client repository allowlist settings, and read timeout settings.
3. [x] Add DockerHub live tag/digest lookup tests with HTTP mocking.
4. [x] Add namespace and repository allowlist enforcement in the RCA evidence collector.
5. [x] Add MCP transient retry helpers with bounded backoff for read-only calls.
6. [x] Add incident timeline events for live evidence collection unavailable, forbidden by allowlist, and timeout outcomes.
7. [x] Add API/readiness dependency checks for Kubernetes MCP, GitHub MCP, and DockerHub configuration.
8. [x] Add documentation for AKS namespace allowlisting and AIRP-client repository allowlisting.
9. [x] Keep GitHub issue creation, Slack sends, remediation PR creation, and documentation publishing disabled.
10. [x] Re-run verification and update this plan after live-read scaffolding is complete.

Verification:

- `./scripts/verify.sh` passes with 50 tests.

## Immediate Next Sprint

Sprint goal: implement the first live Kubernetes MCP and GitHub MCP read transports behind the existing read-only configuration, allowlists, timeouts, and retry guardrails.

Tasks:

1. [ ] Define the concrete MCP HTTP request/response contract for Kubernetes and GitHub read tools.
2. [ ] Add Kubernetes MCP HTTP client transport for `list_pods`, `get_pod`, `get_pod_logs`, `list_events`, `get_deployment`, `get_rollout_status`, and `list_replicasets`.
3. [ ] Add GitHub MCP HTTP client transport for repository metadata, commits, merged PRs, changed files, releases, and prior issues.
4. [ ] Add transport-level tests with `httpx.MockTransport` for success, timeout, 429, 5xx, and malformed payload cases.
5. [ ] Add bounded log-window controls for Kubernetes pod logs by line count and optional time range.
6. [ ] Add MCP evidence source links and collection error details where the upstream transport returns partial data.
7. [ ] Add API readiness details that distinguish configured-but-unreachable from configured-but-not-yet-pinged once active dependency checks are available.
8. [ ] Keep GitHub issue creation, Slack sends, remediation PR creation, and documentation publishing disabled.

## Verified Remaining Critical Path

Verified from the repository on 2026-05-16:

1. Live integrations: implement real Kubernetes MCP and GitHub MCP transports, then validate DockerHub live tag/digest lookup against public AIRP-client images.
2. Governance: wire the existing feature flags, idempotency helper, repository allowlists, and namespace allowlists into future write paths, then add approval policy and blocked-path policy before any GitHub or Slack writes.
3. Agent completion: implement Remediation and Documentation as LangGraph nodes with typed Pydantic outputs, prompts, tests, and workflow states.
4. Memory: add pgvector migration, persist embedding vectors, and switch incident search to vector-backed ranking when query text is present.
5. APIs: add GitHub artifact, Slack message, audit export, policy, discovery refresh, workflow-state, and documentation republish endpoints.
6. Operations: add metrics, health/readiness checks, request/correlation ID middleware, structured logging, CI/CD workflows, scans, SBOM, and AKS production validation.

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

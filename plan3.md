# AIRP Production Completion Plan

This document tracks the remaining work to turn the current AIRP backend/API into a complete, production-ready, end-to-end Autonomous Incident Resolution Platform.

AIRP remains backend/API only. No frontend command center is planned in this backlog.

## Current Baseline

Already implemented:

- FastAPI backend scaffold with modular routes, services, schemas, and settings.
- Microsoft Entra ID authentication boundary.
- SQLAlchemy async models for catalog, repositories, workloads, incidents, events, evidence, approvals, remediation plans, model calls, tool calls, GitHub artifacts, Slack messages, and embeddings.
- SQLAlchemy async model and migration for internal documentation report drafts.
- Alembic initial schema plus incident idempotency migration.
- REST APIs for health, incidents, timelines, audit, services, repositories, workloads, approvals, remediation plan creation/listing, documentation report draft listing, GitHub artifact listing, Slack message listing, and search.
- GenAI Hub adapter with OpenAI-compatible chat, structured chat, embeddings, redaction, retries, and model routing settings.
- Integration boundaries for GitHub MCP, Kubernetes MCP, Slack, and DockerHub.
- Azure Event Hubs Kafka-compatible configuration and JSON event publishing.
- Alertmanager payload normalization.
- Alert ingestion worker for Event Hubs Kafka raw alert topic.
- Redis alert dedupe and PostgreSQL incident idempotency key.
- Dead-letter publishing for malformed alert messages.
- Sample alert publisher script.
- Temporal workflow MVP with workflow IDs on incidents, worker entrypoint, basic workflow state, database status activity, and API workflow signals.
- LangGraph dependency, `src/airp/agents/` package, supervisor, Monitoring Agent node, Correlation Agent node, RCA Agent node, Remediation Agent node, Documentation Agent node, Embedding Agent node, and Temporal `agent_graph_run` activity hook.
- Read-only RCA evidence DTOs and fixture-backed adapters for Kubernetes MCP, GitHub MCP, and DockerHub.
- RCA Agent evidence collector boundary that records planned/completed/unavailable tool calls without mutating external systems.
- RCA evidence bundle sections for Kubernetes, GitHub, DockerHub, and tool calls.
- Temporal `agent_graph_run` persistence for RCA Kubernetes/GitHub/DockerHub evidence items and recorded tool calls.
- RCA hypothesis Pydantic schemas, versioned RCA prompt, structured GenAI Hub hypothesis path, and deterministic low-evidence escalation fallback.
- Temporal `agent_graph_run` persistence for RCA hypotheses and GenAI model-call audit records.
- RCA safety hardening for unsupported claims, low-confidence escalation, prompt-injection text in evidence, and scenario fixtures.
- Read APIs for incident evidence, tool calls, model calls, and RCA hypotheses.
- Read APIs for remediation plans, documentation report drafts, GitHub artifacts, and Slack messages.
- Read API for persisted incident graph embeddings with safe vector metadata.
- Request/correlation ID middleware with response headers and CORS exposure.
- Generic paginated response schema and total-count pagination for incident artifact read APIs: evidence, tool calls, RCA hypotheses, model calls, remediation plans, documentation reports, embeddings, GitHub artifacts, and Slack messages.
- Disabled-by-default external action policy flags and shared artifact idempotency helper for future GitHub, Slack, PR, and documentation writes.
- Remediation Agent LangGraph node with typed output, prompt, deterministic fallback, policy grounding, and internal remediation-plan persistence.
- Documentation Agent LangGraph node with typed report-draft output, prompt, deterministic fallback, and publishing disabled by policy.
- LangGraph supervisor route now runs Monitoring, Correlation, RCA, Remediation, Documentation, and Embedding in sequence.
- Embedding Agent generates redacted graph embeddings for incident, RCA, remediation, and documentation summaries when an embedding client is configured, and Temporal persists them into the existing JSON-backed `incident_embeddings` table.
- Live-read configuration scaffolding for Kubernetes MCP, GitHub MCP, and DockerHub, including endpoint settings, read timeouts, retry settings, namespace/repository allowlists, readiness checks, and failure timeline events.
- Dockerfile, Docker Compose, Helm chart, AKS helper script, migration script, deployment docs, and verification script.
- Helm deployment defaults expose the read-only evidence configuration and use `/api/readiness` for API readiness probing.
- Unit and smoke tests for the implemented foundation.

Still not production complete:

- Full Temporal workflow execution is not complete beyond the MVP workflow skeleton.
- LangGraph supervisor MVP is implemented through Monitoring, Correlation, RCA evidence planning, RCA hypotheses, Remediation planning, Documentation drafting, and Embedding.
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
- Correlation and RCA Agents are implemented as LangGraph nodes.
- Documentation and Remediation agents are implemented as LangGraph node foundations with safe deterministic fallbacks and structured GenAI Hub paths.
- RCA Agent can use a configured read-only evidence collector for Kubernetes MCP, GitHub MCP, and DockerHub evidence.
- RCA Agent generates typed RCA hypotheses with confidence, evidence refs, contradictions, next actions, and escalation decision.
- RCA Agent rejects unsupported or uncited model claims, escalates low-confidence output, and sanitizes untrusted evidence before prompt construction.
- RCA Agent records model-call audit metadata for structured GenAI Hub hypothesis generation.
- Kubernetes, GitHub, and DockerHub evidence clients support fixture-backed reads and typed DTOs for deterministic tests.
- Kubernetes MCP and GitHub MCP clients now carry live-read transport settings, endpoint URLs, read timeouts, and first-pass HTTP read transport methods.
- Kubernetes MCP and GitHub MCP clients implement the first read-only HTTP MCP bridge contract through `POST <endpoint>/tools/call`.
- DockerHub client supports live public tag/digest lookup with configurable timeout and HTTP transport mocking.
- RCA evidence collection enforces configured Kubernetes namespace and GitHub repository allowlists before making read calls.
- RCA evidence collection records unavailable, forbidden, and timeout outcomes as visible incident timeline events.
- RCA evidence persistence stores evidence item payload hashes and tool-call parameter/result hashes.
- RCA fallback reasoning uses DockerHub `source_commit_sha` when present, but full AKS image ID to DockerHub digest to GitHub commit correlation is still pending.
- Current Temporal workflow invokes a LangGraph supervisor through the `agent_graph_run` activity and persists RCA artifacts, proposed remediation plans, and documentation report drafts.
- Current graph embedding output is persisted to `incident_embeddings`; pgvector conversion and semantic ranking remain pending.
- Current GenAI Hub integration is used as an optional LLM/embedding adapter; RCA, Remediation, and Documentation prompt/model-call paths are implemented, while shared prompt loading and production evals are still pending.
- Current verification baseline is `./scripts/verify.sh` with 77 passing tests.

## Remaining Work Summary

The remaining product work is:

- PostgreSQL/pgvector migration verification and production-grade repository/query layer.
- Microsoft Entra ID issuer discovery, JWKS caching, app roles, and route-level authorization.
- Live Azure Event Hubs validation, consumer metrics, and replay/dead-letter operations.
- Temporal workflow hardening: full lifecycle states, retries, workflow replay tests, restart tests, evidence/approval/documentation queries, and external-artifact idempotency.
- AIRP-client discovery: GitHub repositories, DockerHub public image metadata, AKS workload inventory, and repository-to-image-to-workload mapping.
- Kubernetes MCP production validation, read-only AKS identity setup, workload inventory sync, and end-to-end evidence proof against the deployed AKS cluster.
- GitHub MCP write-side implementation for idempotent issues, AIRP-owned branches, safe file reads/writes, draft PRs, PR comments, and artifact persistence.
- Slack notification, signed approval callbacks, threaded updates, replay protection, and approval expiry.
- LangGraph expansion from the current Monitoring, Correlation, RCA evidence/hypothesis, Remediation planning, Documentation drafting, and Embedding MVP into graph checkpoints, graph resume, external artifact governance, and graph execution audit.
- GenAI Hub production agent controls beyond the RCA prompt: shared prompt loading, model fallback policy, token/cost tracking, groundedness rules, prompt-injection hardening, and eval fixtures.
- Incident memory: persisted graph embeddings, pgvector-backed embeddings, semantic search, background embedding jobs, ranking tests, and secret-safe embedding policy.
- End-to-end RCA, remediation, documentation, and knowledge-loop behavior.
- API completion for policy management and remaining paginated list flows.
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
5. Harden LangGraph-based structured GenAI agents with report persistence, checkpoints, resume behavior, graph audit, and governed external-write routing.
6. Add Slack notifications and approval callbacks.
7. Add governed GitHub issue and draft PR creation.
8. Add incident memory persistence, then pgvector-backed semantic search after embedding dimensions are confirmed.
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
- [x] Add pagination response shape: `items`, `limit`, `offset`, `total`.
- [ ] Update list APIs to return paginated responses.
- [ ] Add update endpoints for services, repositories, workloads, incidents, remediation plans, and approvals where appropriate.
- [ ] Add archive semantics for service catalog, repositories, workloads, and stale records.
- [ ] Add database check constraints for incident status, severity, remediation status, risk level, and approval decision.
- [ ] Add optimistic concurrency checks for approval-sensitive writes.
- [x] Add request ID and correlation ID middleware.
- [x] Return request/correlation IDs in every API response.
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
- [x] Add signal-driven closure and escalation workflow states.
- [ ] Add workflow states for correlation, issue creation created, Slack notification sent, remediation planning, approval wait, PR creation, and documentation.
- [x] Implement workflow activities for database state updates.
- [x] Implement workflow activity hook for LangGraph Monitoring, Correlation, RCA planning, Remediation planning, Documentation drafting, and Embedding.
- [x] Persist RCA Kubernetes/GitHub/DockerHub evidence sections and recorded tool calls from `agent_graph_run`.
- [x] Persist RCA hypotheses and RCA model-call audit records from `agent_graph_run`.
- [x] Persist generated Remediation Agent plan records from `agent_graph_run`.
- [x] Persist generated Documentation Agent report drafts from `agent_graph_run`.
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
- [x] Add manual refresh API endpoint.
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
- [x] Implement live `list_pods` through selected MCP transport.
- [x] Implement live `get_pod` through selected MCP transport.
- [x] Implement live `get_pod_logs` through selected MCP transport.
- [x] Implement live `list_events` through selected MCP transport.
- [x] Implement live `get_deployment` through selected MCP transport.
- [x] Implement live `get_rollout_status` through selected MCP transport.
- [x] Implement live `list_replicasets` through selected MCP transport.
- [x] Implement bounded log windows by line count and time range.
- [x] Add request timeout settings.
- [x] Add retry policy for transient MCP failures.
- [x] Redact secrets from collected Kubernetes RCA evidence before storage.
- [x] Hash and store Kubernetes RCA evidence payloads.
- [x] Store Kubernetes RCA evidence in `evidence_items`.
- [x] Add live MCP response schema validation for Kubernetes payloads before storage.
- [x] Add evidence source links where possible.
- [x] Add partial-collection error details when the Kubernetes MCP server returns partial data.
- [x] Add runbook for Kubernetes MCP outage.

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
- [x] Redact and hash stored GitHub RCA evidence payloads.
- [x] Implement live repository listing.
- [x] Implement live repository metadata fetch.
- [x] Implement live branch lookup.
- [x] Implement live commit lookup by SHA.
- [x] Implement live commit lookup by time window.
- [x] Implement live changed-files lookup.
- [x] Implement live merged PR lookup by repository and time window.
- [x] Implement live issue lookup by idempotency marker.
- [ ] Implement issue creation with idempotency.
- [ ] Implement branch creation with safe naming.
- [ ] Implement file read on target branch.
- [ ] Implement file write only on AIRP-created PR branches.
- [ ] Implement draft PR creation with idempotency.
- [ ] Implement PR comment creation.
- [ ] Block merge operations.
- [ ] Block force-push and branch deletion.
- [ ] Block secret file reads where possible.
- [x] Add live MCP response schema validation for GitHub payloads before storage.
- [x] Add partial-collection error details when the GitHub MCP server returns partial data.
- [x] Add runbook for GitHub MCP outage.
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
- [x] Extend LangGraph supervisor routing to Remediation and Documentation agents.
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
- [x] RCA Agent: call live Kubernetes MCP for pods, logs, events, deployments, rollout state, restart count, image ID, and namespace context.
- [x] RCA Agent: call live GitHub MCP for commits, merged PRs, changed files, releases, owners, and prior issues.
- [x] RCA Agent: call live DockerHub client for image tag and digest correlation.
- [x] RCA Agent: build initial evidence-planning bundle from incident, monitoring, catalog, and workload context.
- [x] RCA Agent: extend evidence bundle with Kubernetes, GitHub, and DockerHub evidence.
- [x] RCA Agent: produce ranked hypotheses with confidence, evidence IDs, contradictions, and next actions.
- [ ] RCA Agent: create exactly one idempotent GitHub issue when policy allows.
- [ ] RCA Agent: send Slack incident notification when policy allows.
- [x] Add Remediation Agent graph node.
- [x] Add Remediation Agent prompt and structured output.
- [x] Remediation Agent: read RCA evidence, repository context, and service policy.
- [x] Remediation Agent: generate remediation plan, test plan, rollback plan, risk score, approval requirement, and blocked-path findings.
- [ ] Remediation Agent: enrich planning with created GitHub issue context after issue creation is enabled.
- [ ] Remediation Agent: wait for approval signal before repository write actions.
- [ ] Remediation Agent: create branch and draft PR through GitHub MCP after approval only.
- [x] Add Documentation Agent graph node.
- [x] Add Documentation Agent prompt and structured output.
- [x] Documentation Agent: generate RCA report draft from timeline, evidence, hypotheses, and remediation plan.
- [x] Documentation Agent: store report drafts in PostgreSQL.
- [ ] Documentation Agent: enrich final report with GitHub issue, PR, Slack thread, approval, and outcome after those artifacts exist.
- [ ] Documentation Agent: store final post-closure report and publish to configured wiki target when enabled.
- [x] Add Embedding Agent graph node.
- [x] Add Embedding Agent prompt-free embedding workflow using GenAI Hub `embeddings`.
- [x] Embedding Agent: generate embeddings for incident symptoms and current graph summaries when an embedding client is configured.
- [x] Embedding Agent: include remediation and documentation summaries in graph embedding input.
- [x] Embedding Agent: persist generated graph texts and vectors to `incident_embeddings` with retry-safe idempotency.
- [ ] Embedding Agent: generate embeddings for stored evidence summaries, RCA hypotheses, remediation outcomes, and final report.
- [x] Embedding Agent: redact secret-like content before embedding.
- [ ] Embedding Agent: migrate persisted vectors to PostgreSQL + pgvector once vector dimensions are confirmed.
- [ ] Embedding Agent: retry embedding failures without blocking urgent remediation.
- [x] Add typed Pydantic output schemas for Monitoring and Embedding agents.
- [x] Add typed Pydantic output schemas for Correlation and RCA agents.
- [x] Add typed Pydantic output schemas for Remediation and Documentation agents.
- [x] Persist RCA model calls with prompt version, model name, latency, response hash, validation result, and incident ID.
- [ ] Persist token counts for model calls when gateway usage metadata is available.
- [ ] Add model fallback policy by incident severity.
- [ ] Add token and cost estimation.
- [ ] Add rate-limit and timeout escalation behavior.
- [x] Require RCA hypothesis evidence refs and persist stored evidence ID links when evidence items are stored.
- [x] Require evidence citations for remediation outputs.
- [x] Add deterministic low-evidence escalation fallback for RCA hypotheses.
- [x] Reject unsupported RCA claims from model output.
- [x] Add RCA prompt-injection hardening for Kubernetes logs and GitHub content.
- [ ] Add prompt-injection hardening for Slack text and remaining user-provided fields.
- [ ] Add structured output validation failures to incident timeline.
- [x] Add LangGraph unit tests for supervisor routing.
- [x] Add LangGraph node tests with mocked GenAI Hub and embedding dependencies.
- [x] Add LangGraph node tests with fixture-backed service/workload correlation.
- [x] Add LangGraph RCA node tests with mocked Kubernetes MCP, GitHub MCP, and DockerHub dependencies.
- [x] Add LangGraph node tests for Remediation and Documentation nodes with mocked GenAI Hub outputs and deterministic fallbacks.
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
- [x] Store graph embeddings for incident symptoms, RCA summaries, remediation plans, and documentation drafts in the existing JSON-backed `incident_embeddings` table.
- [x] Add read API for stored incident embeddings with safe text/vector metadata.
- [ ] Store embeddings for stored evidence summaries, RCA hypotheses, remediation outcomes, and final documentation reports.
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
- [x] Collect live Kubernetes pod logs, events, restarts, image IDs, and deployment state.
- [x] Collect fixture-backed GitHub commits, PRs, issues, release metadata, and changed files.
- [x] Collect live GitHub commits, PRs, issues, release metadata, and changed files.
- [x] Collect fixture-backed DockerHub image tag, digest, and source metadata.
- [x] Collect live DockerHub image tag, digest, and source metadata through public tag lookup.
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
- [x] Generate remediation plan from RCA evidence.
- [x] Generate rollback plan.
- [x] Store remediation plan and rollback plan.
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

- [x] Define final RCA report schema.
- [x] Generate report draft from timeline, evidence, hypotheses, and remediation plan.
- [ ] Enrich final report with GitHub issue, PR, Slack thread, approval, and outcome.
- [x] Store report drafts in PostgreSQL.
- [ ] Store final post-closure report in PostgreSQL.
- [ ] Publish report to selected wiki target when configured.
- [x] Add manual republish endpoint.
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

- [x] Add workflow state endpoint.
- [x] Add workflow signal endpoint for pause, resume, approve, reject, escalate, and close.
- [x] Add workflow signal endpoint for retry failed activity.
- [x] Add evidence listing endpoint.
- [x] Add RCA hypothesis listing endpoint.
- [x] Add readiness endpoint for Kubernetes MCP, GitHub MCP, and DockerHub configuration.
- [x] Add GitHub artifact listing endpoint.
- [x] Add Slack message listing endpoint.
- [x] Add model call listing endpoint with safe prompt/response hashes only.
- [x] Add tool call listing endpoint.
- [x] Add incident audit event listing endpoint.
- [x] Add remediation plan listing endpoint.
- [x] Add documentation report listing endpoint.
- [x] Add audit export endpoint.
- [ ] Add policy management endpoint for Admin users.
- [x] Add manual discovery refresh endpoint.
- [x] Add manual documentation republish endpoint.
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
- [x] Add active dependency health checks for PostgreSQL, Redis, Temporal, Event Hubs, GenAI Hub, Kubernetes MCP, GitHub MCP, and DockerHub.
- [ ] Add Slack dependency health check.
- [x] Add readiness behavior that degrades when required dependencies are unavailable.
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
- [x] Add active readiness checks for PostgreSQL, Redis, Temporal, Event Hubs, GenAI Hub, Kubernetes MCP, GitHub MCP, and DockerHub.
- [ ] Add metrics and full health/readiness behavior for API, alert consumer, and Temporal worker.
- [ ] Add Temporal replay tests and worker restart tests.
- [ ] Add graph checkpoints and resume behavior for LangGraph supervisor state.
- [x] Add Kubernetes MCP read DTOs and fixture-backed methods used by RCA Agent.
- [x] Add Kubernetes MCP live-read transport settings, namespace allowlist, read timeout, and retry scaffolding.
- [x] Add live Kubernetes MCP transport methods used by RCA Agent.
- [x] Add GitHub MCP read DTOs and fixture-backed methods used by RCA Agent.
- [x] Add GitHub MCP live-read transport settings, AIRP-client repository allowlist, read timeout, and retry scaffolding.
- [x] Add live GitHub MCP transport methods used by RCA Agent.
- [x] Add DockerHub image evidence DTOs and fixture-backed digest/source metadata lookup.
- [x] Add DockerHub live tag/digest lookup with HTTP mock tests and timeout configuration.
- [x] Add live DockerHub digest/source metadata lookup behavior.
- [ ] Add full AKS image digest to DockerHub digest to GitHub commit correlation behavior.
- [x] Persist Kubernetes, GitHub, and DockerHub evidence items from RCA runs.
- [x] Add structured GenAI RCA hypothesis generation with evidence citations.
- [x] Persist RCA hypotheses and RCA model-call audit records.
- [x] Add API endpoints for evidence, RCA hypotheses, tool calls, and model calls.
- [x] Add RCA golden fixtures and safety tests for unsupported claims, low-confidence output, and prompt-injection text.
- [x] Add disabled-by-default external action policy flags and shared idempotency helper.
- [ ] Add idempotent GitHub issue creation after RCA policy allows it.
- [ ] Add Slack notification, signed approval callback, replay protection, and threaded updates.
- [x] Add Remediation Agent graph node foundation with typed schema, policy grounding, safe planning, and internal plan persistence.
- [ ] Add Remediation Agent approval wait, branch creation, blocked-path policy, and draft PR creation.
- [x] Add Documentation Agent graph node foundation with typed schema and report draft generation.
- [x] Add Documentation Agent report-draft persistence.
- [ ] Add Documentation Agent final RCA report storage, publishing, and embedding.
- [x] Persist graph embeddings to `incident_embeddings` and expose an incident embeddings read API.
- [ ] Add vector-backed semantic search and ranking tests.
- [x] Add API endpoints for remediation plan listing and documentation report listing.
- [x] Add API endpoint for incident embeddings.
- [x] Add API endpoints for GitHub artifacts and Slack messages.
- [x] Add API endpoint for audit export.
- [x] Add API endpoints for discovery refresh and report republish.
- [ ] Add API endpoints for policy management.
- [ ] Add CI/CD workflows for lint, tests, migrations, Docker build, image scanning, SBOM, Helm checks, release, deployment, and rollback.
- [ ] Deploy and validate AIRP API, alert consumer, and Temporal worker on Azure AKS with Kubernetes secrets and production auth.
- [ ] Run end-to-end simulations for latency, crash loop, bad config, and failed deployment incidents.
- [ ] Complete production runbooks and handoff documentation.

## Verified Remaining Task Inventory

This inventory was re-verified against the repository on 2026-05-16. It is the consolidated list of remaining product work after the completed read-only RCA, structured RCA, safety, live-read configuration, active readiness, Remediation/Documentation foundation, and documentation persistence/API sprints.

Foundation and data:

- [ ] Run all Alembic migrations against real PostgreSQL 16.
- [ ] Add pgvector extension migration and convert `incident_embeddings.vector` from JSON to `pgvector.Vector`.
- [ ] Confirm GenAI Hub embedding dimensions before vector migration.
- [x] Add `documentation_reports` model, schemas, migration, service methods, and retention metadata.
- [x] Add incident embedding create/read schemas and service methods over the existing JSON-backed `incident_embeddings` table.
- [ ] Add repository-layer query classes for incidents, catalog, approvals, evidence, model calls, tool calls, GitHub artifacts, and Slack messages.
- [ ] Add repository-layer query classes for remediation plans, documentation reports, and incident embeddings.
- [x] Add total-count pagination response models for incident artifact read APIs.
- [ ] Extend paginated responses to remaining catalog, incident, search, workflow, and future artifact list APIs where appropriate.
- [ ] Add update/archive semantics for catalog, repositories, workloads, incidents, remediation plans, and approvals where appropriate.
- [ ] Add database check constraints and optimistic concurrency for approval-sensitive writes.
- [x] Add request ID and correlation ID middleware with response headers.
- [ ] Add structured audit events for every mutating API route.

Authentication and authorization:

- [ ] Add Entra issuer discovery and JWKS caching/rotation behavior.
- [ ] Validate `nbf`, required `tid`, and required app roles.
- [ ] Define and enforce `AIRP.Admin`, `AIRP.SRE`, `AIRP.Viewer`, and `AIRP.Approver`.
- [ ] Add route-level RBAC for catalog/admin, incident mutation, approval decisions, and read-only access.
- [ ] Add signed JWT fixtures and negative auth tests.
- [ ] Document Entra app registration, scopes, roles, and local token acquisition.

Event Hubs and ingestion:

- [ ] Provision raw alert, validated incident, agent event, and dead-letter Event Hubs topics.
- [ ] Validate the alert consumer and sample publisher against the real Azure Event Hubs Kafka endpoint.
- [ ] Add alert consumer liveness/readiness and operational metrics.
- [ ] Add replay and dead-letter inspection/replay tooling.
- [ ] Add a local Kafka-compatible integration test profile when available.

Temporal workflow:

- [ ] Add full lifecycle workflow states for correlation, issue creation, Slack notification, remediation, approval wait, PR creation, documentation, and completion.
- [ ] Add dedicated activities for live evidence collection, GitHub issue creation, Slack notification, remediation, approval handling, PR creation, documentation, and closure.
- [ ] Add retry-failed-activity signal and workflow queries for evidence summary, approval request, and timeline.
- [ ] Add activity-specific retry policies, non-retryable error classes, and heartbeat handling.
- [ ] Add workflow replay tests and worker restart tests.
- [ ] Add idempotency keys to every future external-write activity.

Discovery and mapping:

- [ ] Implement AIRP-client GitHub repository discovery with owners, default branch, topics, CODEOWNERS, archived state, and visibility.
- [ ] Implement DockerHub public tag listing and image provenance capture.
- [ ] Implement AKS workload inventory sync through Kubernetes MCP.
- [ ] Persist repository-to-image-to-workload mappings.
- [ ] Detect unmapped running images and repositories with images not running in AKS.
- [ ] Add scheduled discovery worker, manual refresh API, discovery audit events, and fixture tests.

Live read integrations:

- [x] Define the concrete MCP HTTP request/response contract for Kubernetes and GitHub read tools.
- [x] Implement live Kubernetes MCP reads for pods, pod details, logs, events, deployments, rollout status, and replica sets.
- [x] Implement bounded Kubernetes log windows by line count and optional time range.
- [x] Implement live GitHub MCP reads for repository metadata, branches, commits, changed files, merged PRs, releases, and prior issues.
- [x] Add live MCP response schema validation before evidence storage.
- [x] Add evidence source links where possible.
- [x] Add partial-collection error details when upstream MCP transports return partial data.
- [x] Add transport-level tests for success, timeout, 429, 5xx, and malformed payloads.

Agent layer:

- [x] Add Remediation Agent as a LangGraph node with typed schema, prompt, tests, and policy guardrails.
- [x] Persist generated Remediation Agent plan records internally without external writes.
- [ ] Add Remediation Agent approval wait and draft PR path.
- [x] Add Documentation Agent as a LangGraph node with typed schema, prompt, tests, report draft generation, and publishing flag.
- [x] Add Documentation Agent report-draft persistence.
- [ ] Add Documentation Agent final RCA report storage and embedding path.
- [x] Persist Embedding Agent graph output to `incident_embeddings`.
- [ ] Add graph checkpoints, graph resume behavior, graph versioning, and graph execution trace export.
- [ ] Add graph-level timeout, retry, escalation, and idempotency rules.
- [ ] Add shared prompt template loader and versioning beyond the RCA prompt.
- [ ] Add token counts, cost estimates, model fallback policy, rate-limit handling, and model-timeout escalation.
- [ ] Persist embeddings for stored evidence summaries, RCA hypotheses, remediation outcomes, and final reports.
- [ ] Add vector-backed incident memory and semantic ranking.

Governed external actions:

- [ ] Add idempotent GitHub issue creation after policy allows it.
- [ ] Add Slack incident notification, signed callbacks, threaded updates, approval actions, expiry, and replay protection.
- [ ] Add remediation policy schema, risk levels, blocked paths, protected-branch rules, and required tests.
- [ ] Add branch creation, AIRP-owned branch writes, draft PR creation, PR comments, CI tracking, and PR artifact persistence.
- [ ] Keep merge, force-push, destructive branch actions, and unsafe secret-file reads blocked.

API completion:

- [x] Add workflow state endpoint and retry-failed-activity signal endpoint.
- [x] Add remediation plan listing endpoint.
- [x] Add documentation report listing endpoint.
- [x] Add incident embedding listing endpoint.
- [x] Add GitHub artifact and Slack message listing endpoints.
- [x] Add audit export endpoint.
- [ ] Add Admin policy management endpoint.
- [x] Add discovery refresh and documentation republish endpoints.
- [ ] Add OpenAPI examples for production APIs.

Operations, security, deployment, and handoff:

- [ ] Add OpenTelemetry instrumentation, Prometheus metrics, and Grafana dashboards.
- [x] Add active dependency health checks for PostgreSQL, Redis, Temporal, Event Hubs, GenAI Hub, Kubernetes MCP, GitHub MCP, and DockerHub.
- [ ] Add Slack dependency health check.
- [x] Add readiness behavior that degrades when required dependencies are unavailable.
- [ ] Add request body limits, rate limiting, production CORS validation, and security headers.
- [ ] Add CI/CD for lint, tests, migrations, Docker build, image scanning, SBOM, Helm checks, release, deploy, and rollback.
- [ ] Deploy API, alert consumer, and Temporal worker to Azure AKS with production auth and Kubernetes secrets.
- [ ] Run end-to-end incident simulations for latency, crash loop, bad config, and failed deployment scenarios.
- [ ] Complete runbooks, onboarding guide, rollback guide, and production readiness checklist.

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

## Completed Sprint: MCP HTTP Read Transport Foundation

Sprint goal: implement the first live Kubernetes MCP and GitHub MCP read transports behind the existing read-only configuration, allowlists, timeouts, and retry guardrails.

Tasks:

1. [x] Define the concrete MCP HTTP request/response contract for Kubernetes and GitHub read tools.
2. [x] Add Kubernetes MCP HTTP client transport for `list_pods`, `get_pod`, `get_pod_logs`, `list_events`, `get_deployment`, `get_rollout_status`, and `list_replicasets`.
3. [x] Add GitHub MCP HTTP client transport for repository metadata, branches, commit-by-SHA, commits by time window, merged PRs, changed files, releases, and prior issues.
4. [x] Add transport-level tests with `httpx.MockTransport` for success, timeout, 429, 5xx, and malformed payload cases.
5. [x] Add bounded log-window controls for Kubernetes pod logs by line count and optional time range.
6. [x] Add MCP evidence source links where available.
7. [x] Add API readiness details that mark MCP reachability as `not_checked` until active dependency checks are implemented.
8. [x] Keep GitHub issue creation, Slack sends, remediation PR creation, and documentation publishing disabled.

Verification:

- `./scripts/verify.sh` passes with 56 tests.

## Completed Sprint: Active Readiness and Partial Evidence Resilience

Sprint goal: add active dependency checks and partial-collection resilience around the live read transports.

Tasks:

1. [x] Add active readiness probes for Kubernetes MCP, GitHub MCP, DockerHub, GenAI Hub, Redis, PostgreSQL, Temporal, and Event Hubs without leaking secrets.
2. [x] Make `/api/readiness` degrade when required dependencies are unreachable.
3. [x] Preserve upstream MCP partial-collection warnings and errors in `collection_errors`.
4. [x] Add timeline events for partial evidence collection with usable evidence.
5. [x] Add runbooks for Kubernetes MCP, GitHub MCP, DockerHub, and GenAI Hub outages.
6. [x] Keep GitHub issue creation, Slack sends, remediation PR creation, and documentation publishing disabled.

Verification:

- `./scripts/verify.sh` passes with 61 tests.

## Completed Sprint: Remediation and Documentation Agent Foundations

Sprint goal: add Remediation and Documentation LangGraph node foundations without enabling external writes.

Tasks:

1. [x] Define typed Remediation Agent output schema with remediation plan, rollback plan, test plan, risk score, approval requirement, and blocked-path findings.
2. [x] Implement Remediation Agent LangGraph node that reads RCA hypotheses, evidence summaries, repository context, and policy flags.
3. [x] Persist generated remediation plan records without creating branches or PRs.
4. [x] Define typed Documentation Agent output schema for final RCA report drafts.
5. [x] Implement Documentation Agent LangGraph node that drafts a final report from timeline, evidence, hypotheses, and remediation plan when invoked.
6. [x] Extend the supervisor graph routing to include Remediation and Documentation nodes behind safe policy gates.
7. [x] Add unit tests for Remediation and Documentation nodes with mocked GenAI Hub outputs and deterministic fallbacks.
8. [x] Keep GitHub issue creation, Slack sends, remediation PR creation, and documentation publishing disabled.

Verification:

- `ruff check src tests` passes.
- `pytest tests/unit/test_agents.py -q` passes with 11 tests.
- `./scripts/verify.sh` passes with 65 tests.

## Completed Sprint: Documentation Persistence and Artifact Read APIs

Sprint goal: persist documentation drafts and expose remediation/documentation artifacts through backend APIs without enabling external publishing.

Tasks:

1. [x] Add a PostgreSQL model, schema, and migration for RCA documentation report drafts.
2. [x] Persist Documentation Agent report drafts from `agent_graph_run`.
3. [x] Add `GET /api/incidents/{incident_id}/remediation-plans` for operator inspection.
4. [x] Add `GET /api/incidents/{incident_id}/documentation-reports` for report draft inspection.
5. [x] Extend Embedding Agent input collection to include remediation summaries and documentation drafts while keeping pgvector persistence pending.
6. [x] Add unit and API tests for remediation plan listing and documentation report persistence.
7. [x] Keep wiki publishing, Slack sends, GitHub issue creation, and remediation PR creation disabled until approval and policy layers are complete.

Verification:

- `ruff check src tests` passes.
- Focused tests for agents, agent persistence, and backend smoke pass with 17 tests.
- `./scripts/verify.sh` passes with 68 tests.

## Completed Sprint: Graph Embedding Persistence

Sprint goal: persist graph embeddings into the existing `incident_embeddings` table while keeping pgvector conversion pending until embedding dimensions are confirmed.

Tasks:

1. [x] Add incident embedding create/read schemas and service methods.
2. [x] Persist `embedding_texts` and `embedding_vectors` from `agent_graph_run` into `incident_embeddings`.
3. [x] Add `GET /api/incidents/{incident_id}/embeddings` with safe text and vector metadata.
4. [x] Add idempotency for embedding persistence across workflow retries.
5. [x] Add tests for embedding persistence, redaction, and API route registration.
6. [x] Keep pgvector conversion, semantic ranking, and vector search pending until GenAI Hub embedding dimensions are confirmed.

Verification:

- `ruff check` for touched embedding persistence/API files passes.
- Focused tests for agent persistence and backend smoke pass with 7 tests.
- `./scripts/verify.sh` passes with 70 tests.

## Completed Sprint: Request IDs and Paginated Artifact Responses

Sprint goal: harden core API ergonomics with request/correlation ID middleware and paginated incident artifact read responses.

Tasks:

1. [x] Add request ID and correlation ID middleware with response headers.
2. [x] Add reusable generic `Page[T]` response schema for incident artifact list endpoints.
3. [x] Add total-count query helpers for incident evidence, tool calls, model calls, hypotheses, remediation plans, documentation reports, and embeddings.
4. [x] Update incident artifact list APIs to return `items`, `limit`, `offset`, and `total`.
5. [x] Add tests for request/correlation ID propagation and paginated artifact response models.
6. [x] Add OpenAPI examples for the newly paginated incident artifact endpoints.

Verification:

- Focused `ruff check` for touched API, middleware, schema, service, and smoke-test files passes.
- `pytest tests/integration/test_backend_smoke.py -q` passes with 7 tests.
- `./scripts/verify.sh` passes with 72 tests.

## Completed Sprint: GitHub and Slack Artifact Read APIs

Sprint goal: expose remaining persisted external-artifact records through backend APIs without enabling new GitHub or Slack writes.

Tasks:

1. [x] Add read schemas for persisted GitHub artifacts and Slack messages.
2. [x] Add service list/count helpers for `github_artifacts` and `slack_messages`.
3. [x] Add `GET /api/incidents/{incident_id}/github-artifacts` with paginated response metadata.
4. [x] Add `GET /api/incidents/{incident_id}/slack-messages` with paginated response metadata.
5. [x] Add smoke tests for route registration and response models.
6. [x] Keep issue creation, Slack sends, branch creation, PR creation, and documentation publishing disabled until approval/policy gates are complete.

Verification:

- Focused `ruff check` for touched API, schema, service, and smoke-test files passes.
- `pytest tests/integration/test_backend_smoke.py -q` passes with 7 tests.
- `./scripts/verify.sh` passes with 72 tests.

## Completed Sprint: Workflow Visibility and Audit Export APIs

Sprint goal: add workflow visibility and operator export surfaces without changing incident execution behavior.

Tasks:

1. [x] Add `GET /api/incidents/{incident_id}/workflow/state` for current workflow ID, run ID, incident status, and latest workflow-related timeline event.
2. [x] Add a retry-failed-activity workflow signal contract without invoking retries until Temporal support is complete.
3. [x] Add audit export endpoint for incident events with JSON response first.
4. [x] Add tests for workflow-state route registration, response schema, and audit export shape.
5. [x] Update OpenAPI examples for workflow state and audit export.
6. [x] Keep workflow execution, retry activity behavior, and external writes unchanged until workflow hardening is complete.

Verification:

- Focused `ruff check` for touched API, schema, service, and workflow test files passes.
- Focused smoke and Temporal workflow tests pass with 12 tests.
- `./scripts/verify.sh` passes with 75 tests.

## Completed Sprint: Audit-Only Operator Control APIs

Sprint goal: add safe operator control endpoints for manual refresh and documentation republish requests without enabling external side effects.

Tasks:

1. [x] Add request schemas for manual discovery refresh and documentation republish commands.
2. [x] Add `POST /api/services/refresh` as an audit-only command acknowledgement.
3. [x] Add `POST /api/incidents/{incident_id}/documentation-reports/{report_id}/republish` that records a republish request only.
4. [x] Add response schemas that clearly mark external execution as `pending_implementation` or `disabled_by_policy`.
5. [x] Add route registration and response-shape tests.
6. [x] Keep discovery jobs, wiki publishing, Slack sends, GitHub writes, and repository writes disabled until policy and worker support are complete.

Verification:

- Focused `ruff check` for touched API, schema, service, and smoke-test files passes.
- `pytest tests/integration/test_backend_smoke.py -q` passes with 11 tests.
- `./scripts/verify.sh` passes with 77 tests.

## Immediate Next Sprint

Sprint goal: add read-only policy visibility so operators can inspect the disabled-by-default automation guardrails before write paths are implemented.

Tasks:

1. [ ] Add policy read schemas for GitHub issue creation, Slack notification, remediation PR creation, documentation publishing, repository allowlists, namespace allowlists, and MCP read settings.
2. [ ] Add `GET /api/policy` or equivalent Admin policy endpoint returning effective runtime settings without secrets.
3. [ ] Add OpenAPI examples for the effective policy response.
4. [ ] Add tests that policy responses redact secrets and preserve disabled-by-default write flags.
5. [ ] Keep policy mutation, GitHub writes, Slack sends, wiki publishing, branch creation, and PR creation disabled.

## Verified Remaining Critical Path

Verified from the repository on 2026-05-16:

1. Live validation: validate Kubernetes MCP, GitHub MCP, and DockerHub read transports against deployed AIRP-client infrastructure and public AIRP-client images.
2. Governance: wire the existing feature flags, idempotency helper, repository allowlists, and namespace allowlists into future write paths, then add approval policy and blocked-path policy before any GitHub or Slack writes.
3. Agent completion: extend the Remediation and Documentation nodes with approval workflow states, final artifact enrichment, and governed external writes.
4. Memory: add pgvector migration, confirm embedding dimensions, and switch incident search to vector-backed ranking when query text is present.
5. APIs: add policy and remaining paginated list endpoints.
6. Operations: add metrics, health/readiness checks, structured logging with request/correlation IDs, CI/CD workflows, scans, SBOM, and AKS production validation.

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

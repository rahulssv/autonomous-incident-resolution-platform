# AIRP Remaining Product Build Plan

## Current State

The repository now has a backend/API foundation:

- FastAPI application scaffold.
- Microsoft Entra ID JWT validation boundary.
- SQLAlchemy models for service catalog, repositories, workloads, incidents, evidence, approvals, remediation plans, model calls, and tool calls.
- Alembic initial migration.
- REST routes for health, incidents, audit timeline, services, repositories, workloads, approvals, and search.
- GenAI Hub adapter with redaction, retries, chat, structured chat, and embeddings.
- DockerHub public metadata client.
- GitHub MCP, Kubernetes MCP, and Slack adapter boundaries.
- Azure Event Hubs Kafka-compatible configuration helper.
- Dockerfile, Docker Compose, Helm chart, deployment docs, and verification script.
- Basic tests and linting.

This is not yet a complete autonomous incident resolution product. The remaining work is mostly workflow execution, real integrations, agent behavior, production security, observability, and end-to-end validation.

## Build Strategy

Build in vertical product slices, not isolated infrastructure chunks. Each milestone should create one usable behavior that can be demonstrated from input to output.

Priority order:

1. Make the backend persistent and deployable against real PostgreSQL.
2. Connect Azure Event Hubs alert ingestion.
3. Add Temporal workflow execution.
4. Implement real MCP, Slack, DockerHub, and GenAI Hub usage inside agents.
5. Add production-grade auditability, policy enforcement, and end-to-end tests.

## Milestone 1: Persistence and API Hardening

Goal: make the current API production-safe against PostgreSQL and ready for real users.

Tasks:

- [ ] Verify Alembic migration against PostgreSQL 16 + pgvector.
- [ ] Add `CREATE EXTENSION IF NOT EXISTS vector` migration step.
- [ ] Replace JSON placeholder vector storage with `pgvector.Vector` once embedding dimensions are confirmed.
- [ ] Add repository layer classes for incident, catalog, approval, evidence, model-call, and tool-call queries.
- [ ] Add pagination response shape with `items`, `limit`, `offset`, and `total`.
- [ ] Add update endpoints for services, repositories, workloads, incidents, and remediation plans.
- [ ] Add delete/archive semantics for service catalog records.
- [ ] Add database constraints for status, severity, risk level, and approval decision values.
- [ ] Add optimistic concurrency or updated-at checks for approval-sensitive records.
- [ ] Add API request IDs and correlation IDs on every response.
- [ ] Add structured audit event creation to every mutating API route.
- [ ] Add OpenAPI examples for core request/response bodies.
- [ ] Add integration tests that run against Docker Compose PostgreSQL, not SQLite.

Acceptance criteria:

- `docker compose up` starts PostgreSQL, Redis, Temporal, and API.
- `alembic upgrade head` succeeds from an empty database.
- A service, repository, workload, incident, approval, evidence item, and remediation plan can be created and queried.
- Every mutation creates an audit event.
- Tests pass against real PostgreSQL in CI.

## Milestone 2: Microsoft Entra ID Production Auth

Goal: enforce enterprise authentication and authorization correctly.

Tasks:

- [ ] Add Entra ID issuer discovery from `/.well-known/openid-configuration`.
- [ ] Cache JWKS keys with refresh on key rotation.
- [ ] Validate `aud`, `iss`, `exp`, `iat`, `nbf`, `tid`, and app roles.
- [ ] Define AIRP app roles: `AIRP.Admin`, `AIRP.SRE`, `AIRP.Viewer`, `AIRP.Approver`.
- [ ] Add route-level role requirements.
- [ ] Add authorization tests with signed test JWTs.
- [ ] Add docs for Entra app registration, exposed API scopes, and app roles.
- [ ] Add local token acquisition instructions for developers.
- [ ] Add production failure behavior for missing/invalid auth configuration.

Acceptance criteria:

- Protected routes reject missing, expired, wrong-audience, and wrong-issuer tokens.
- Viewer can read but cannot mutate.
- Approver can approve or reject approval requests.
- Admin can manage catalog and policy.

## Milestone 3: Azure Event Hubs Kafka Alert Ingestion

Goal: transform Prometheus/Alertmanager events into durable AIRP incidents.

Tasks:

- [x] Define Pydantic event contracts for `airp.alerts.raw`, `airp.incidents.validated`, and `airp.deadletter`.
- [x] Implement Kafka JSON producer wrapper.
- [x] Implement Kafka consumer loop for Azure Event Hubs.
- [x] Add configurable topic names and consumer group IDs.
- [x] Implement Alertmanager webhook payload normalization.
- [x] Implement dedupe key generation from service, namespace, alert name, severity, and time window.
- [x] Store dedupe keys in Redis with TTL.
- [x] Create incidents from validated alert events.
- [x] Publish dead-letter events for malformed payloads.
- [x] Add replay-safe idempotency for incident creation.
- [x] Add alert ingestion worker entrypoint.
- [x] Add tests for alert normalization, dedupe, and event publishing.
- [x] Add tests for idempotent database incident creation and dead-letter publishing.

Acceptance criteria:

- A sample Alertmanager alert creates exactly one incident.
- Replaying the same event does not create a duplicate incident.
- Invalid events go to dead-letter with an explainable error.

## Milestone 4: Temporal Workflow Execution

Goal: move incident lifecycle from static API state to durable workflow state.

Tasks:

- [ ] Add Temporal client configuration.
- [ ] Add Temporal worker entrypoint.
- [ ] Implement `IncidentWorkflow`.
- [ ] Implement activities for monitoring, correlation, RCA evidence collection, remediation planning, approval waiting, PR creation, documentation, and closure.
- [ ] Use idempotency keys for Slack messages, GitHub issues, GitHub PRs, and incident events.
- [ ] Add workflow signals: pause, resume, escalate, approve, reject, close.
- [ ] Add workflow queries for current state and timeline.
- [ ] Persist workflow IDs on incidents.
- [ ] Emit `airp.agent.events` from workflow activities.
- [ ] Add retry, timeout, and non-retryable error policies.
- [ ] Add workflow replay tests.

Acceptance criteria:

- Validated incident starts a Temporal workflow.
- Worker restart does not lose progress.
- Approval timeout moves workflow to `ESCALATED`.
- Workflow state and database state remain consistent.

## Milestone 5: Service Catalog and Environment Discovery

Goal: automatically understand the AIRP-client environment.

Tasks:

- [ ] Implement AIRP-client GitHub organization repository discovery.
- [ ] Map repositories to service names, owners, default branches, CODEOWNERS, and DockerHub image names.
- [ ] Implement AKS workload inventory sync through Kubernetes MCP.
- [ ] Capture namespace, deployment, replica set, pod, container, image tag, image ID, restart count, readiness, and node.
- [ ] Implement DockerHub tag and digest lookup for public images.
- [ ] Correlate `runtime_workloads.image_id` to DockerHub digest.
- [ ] Persist repository-to-image-to-workload mappings.
- [ ] Add scheduled refresh worker.
- [ ] Add manual refresh API endpoint.
- [ ] Add mismatch detection when a running image cannot be mapped to a repository.

Acceptance criteria:

- AIRP can list AIRP-client repositories.
- AIRP can list AKS workloads and container images.
- AIRP can map a running pod image to a DockerHub image and likely repository.

## Milestone 6: Kubernetes MCP Integration

Goal: collect reliable runtime evidence from Azure AKS.

Tasks:

- [ ] Choose Kubernetes MCP transport and authentication pattern.
- [ ] Configure dedicated read-only AKS identity.
- [ ] Implement `list_pods`, `get_pod`, `get_pod_logs`, `list_events`, `get_deployment`, `get_rollout_status`, and `list_replicasets`.
- [ ] Add namespace allowlist.
- [ ] Add request timeouts and bounded log windows.
- [ ] Redact secrets from logs before storage or LLM use.
- [ ] Store Kubernetes evidence items with source links and hashes.
- [ ] Add tests with fixture Kubernetes responses.
- [ ] Add operational runbook for Kubernetes MCP outage.

Acceptance criteria:

- RCA workflow can fetch pod logs, events, restarts, image IDs, and deployment state.
- Evidence is stored without secrets.
- MCP timeout escalates gracefully.

## Milestone 7: GitHub MCP Integration

Goal: connect incidents to AIRP-client repository history and create governed GitHub artifacts.

Tasks:

- [ ] Choose GitHub MCP transport and authentication pattern.
- [ ] Configure org-scoped least-privilege credentials for `AIRP-client`.
- [ ] Implement repository listing.
- [ ] Implement commit lookup by SHA, branch, time window, and file path.
- [ ] Implement merged PR lookup by repository and time window.
- [ ] Implement issue creation with idempotency.
- [ ] Implement branch creation.
- [ ] Implement file read/write through PR branch only.
- [ ] Implement draft PR creation.
- [ ] Implement PR comment creation.
- [ ] Block merge, force-push, delete branch, and secret access.
- [ ] Store all GitHub artifacts in `github_artifacts`.
- [ ] Add tests with MCP fixture responses.

Acceptance criteria:

- RCA Agent creates one GitHub issue per incident.
- Replayed workflow does not create duplicate issues.
- Remediation Agent can create a draft PR only after approval.

## Milestone 8: Slack Integration and Approval UX

Goal: make incident notification and approval usable for SREs.

Tasks:

- [ ] Configure Slack app credentials.
- [ ] Implement incident notification message formatting.
- [ ] Implement threaded updates for RCA progress, issue creation, remediation plan, approval request, and PR creation.
- [ ] Implement signed approval payload generation.
- [ ] Implement approval callback endpoint.
- [ ] Verify approval payload hash before action execution.
- [ ] Add approval expiry and replay protection.
- [ ] Store Slack channel, message timestamp, thread timestamp, and permalink.
- [ ] Add tests for payload signing and replay rejection.

Acceptance criteria:

- RCA creates a Slack incident thread.
- SRE can approve or reject from Slack.
- Approval cannot be replayed or modified.

## Milestone 9: GenAI Hub Production Agent Layer

Goal: turn the LLM adapter into reliable agent intelligence.

Tasks:

- [ ] Define prompt templates for Monitoring, Correlation, RCA, Remediation, and Documentation agents.
- [ ] Version prompt templates.
- [ ] Define Pydantic structured outputs for every agent response.
- [ ] Add model-call persistence for prompts, model names, latency, token counts, response hash, and validation result.
- [ ] Add model fallback policy by severity.
- [ ] Add cost and token estimation.
- [ ] Add rate-limit handling and escalation.
- [ ] Add groundedness rules requiring evidence citations.
- [ ] Add prompt-injection hardening for logs, GitHub content, and Kubernetes events.
- [ ] Add LLM eval fixtures for known incident scenarios.

Acceptance criteria:

- Every agent response validates against a schema.
- RCA hypotheses cite stored evidence IDs.
- Low-confidence or unsupported conclusions escalate instead of creating remediation plans.

## Milestone 10: Correlation and pgvector Incident Memory

Goal: improve RCA using historical incidents and searchable memory.

Tasks:

- [ ] Enable pgvector in migration.
- [ ] Choose and document embedding dimensions for GenAI Hub `embeddings`.
- [ ] Convert `incident_embeddings.vector` to pgvector type.
- [ ] Generate embeddings for incident symptoms, RCA summaries, remediation outcomes, and postmortems.
- [ ] Implement semantic search using vector similarity.
- [ ] Combine vector score with service match, recency, and remediation success.
- [ ] Add `GET /api/search/incidents` vector-backed behavior.
- [ ] Add background embedding jobs.
- [ ] Add tests for ranking behavior.

Acceptance criteria:

- Similar historical incidents are returned for a new incident.
- Correlation Agent includes prior fixes and outcomes in RCA context.

## Milestone 11: RCA Agent End-to-End

Goal: produce evidence-backed root cause analysis and issue creation.

Tasks:

- [ ] Implement RCA activity orchestration.
- [ ] Collect Kubernetes logs/events/deployment evidence.
- [ ] Collect GitHub commits/PRs/issues/release metadata.
- [ ] Correlate AKS pod image to DockerHub digest and GitHub commit.
- [ ] Build RCA evidence bundle.
- [ ] Invoke GenAI Hub with structured RCA schema.
- [ ] Store ranked hypotheses.
- [ ] Create GitHub issue in affected repository.
- [ ] Send Slack notification.
- [ ] Update incident status to `RCA_ISSUE_CREATED` and `SLACK_NOTIFIED`.
- [ ] Add golden tests for high latency, crash loop, bad deployment, and config error incidents.

Acceptance criteria:

- A synthetic incident produces a GitHub issue and Slack notification with cited evidence.
- The issue links back to the AIRP incident and includes affected pod/image/commit context.

## Milestone 12: Remediation Agent End-to-End

Goal: create safe, approved remediation PRs.

Tasks:

- [ ] Define remediation policy: risk levels, max changed files, protected files, required tests, required approval.
- [ ] Implement remediation plan generation.
- [ ] Store remediation plans and rollback plans.
- [ ] Request approval before PR creation.
- [ ] Wait for approval signal from API or Slack.
- [ ] Create branch through GitHub MCP.
- [ ] Generate minimal code/config diff.
- [ ] Create draft PR with test plan and rollback plan.
- [ ] Link PR to issue and incident.
- [ ] Track CI status and update incident timeline.
- [ ] Escalate if proposed change touches blocked files or exceeds risk policy.

Acceptance criteria:

- Remediation Agent cannot create a PR without approval when approval is required.
- Approved remediation creates a linked draft PR.
- PR body includes RCA evidence, tests, rollback, risk level, and approval record.

## Milestone 13: Documentation Agent and Knowledge Loop

Goal: close every incident with a reusable RCA artifact.

Tasks:

- [ ] Define RCA report schema.
- [ ] Generate final RCA report from incident timeline, evidence, hypotheses, issue, PR, Slack thread, and outcome.
- [ ] Publish documentation to selected wiki target.
- [ ] Store final report in PostgreSQL.
- [ ] Create embeddings for final report.
- [ ] Generate prevention follow-up tasks.
- [ ] Add report publishing retry behavior.
- [ ] Add manual republish endpoint.

Acceptance criteria:

- Closed incident has final RCA report.
- Report is searchable through incident memory.
- Documentation failure does not block urgent remediation but remains retryable.

## Milestone 14: Observability and Operations

Goal: make AIRP observable, debuggable, and supportable.

Tasks:

- [ ] Add OpenTelemetry FastAPI instrumentation.
- [ ] Add Prometheus metrics endpoint.
- [ ] Track request count, latency, error count, workflow count, agent latency, model tokens, model failures, MCP failures, and approval latency.
- [ ] Add structured logging with incident ID and correlation ID.
- [ ] Add health checks for PostgreSQL, Redis, Temporal, Event Hubs, GenAI Hub, Kubernetes MCP, GitHub MCP, and Slack.
- [ ] Add readiness behavior that fails when required dependencies are unavailable.
- [ ] Add dashboard JSON or Grafana provisioning docs.
- [ ] Add runbooks for common failures.

Acceptance criteria:

- Operators can identify dependency failures from health endpoints and metrics.
- Every incident workflow has correlated logs.

## Milestone 15: Security Hardening

Goal: satisfy production security requirements.

Tasks:

- [ ] Add secret scanning to CI.
- [ ] Add dependency vulnerability scanning.
- [ ] Add container image scanning.
- [ ] Add SBOM generation.
- [ ] Add request body size limits.
- [ ] Add rate limiting for public/API endpoints.
- [ ] Add CORS production allowlist.
- [ ] Add response security headers.
- [ ] Add policy to block LLM prompts containing secret-like content.
- [ ] Add MCP parameter hashing for sensitive tool calls.
- [ ] Add audit export endpoint.
- [ ] Add branch protection and required checks documentation for AIRP-client repos.

Acceptance criteria:

- Secrets are blocked from prompts, logs, issues, Slack messages, PRs, and embeddings.
- Security scan is part of CI.
- Audit trail can reconstruct every model call, tool call, approval, and repository write.

## Milestone 16: CI/CD and Release Automation

Goal: make every release repeatable.

Tasks:

- [ ] Add GitHub Actions workflow for lint, tests, and migrations.
- [ ] Add Docker build workflow.
- [ ] Push AIRP backend image to DockerHub or approved registry.
- [ ] Add Helm lint and template checks.
- [ ] Add deployment workflow to AKS.
- [ ] Add migration execution step for production.
- [ ] Add release tagging and changelog generation.
- [ ] Add rollback workflow.
- [ ] Add environment-specific values files.

Acceptance criteria:

- Main branch cannot merge unless tests and lint pass.
- Tagged release builds and publishes image.
- AKS deployment can be rolled back.

## Milestone 17: Production Deployment on Azure AKS

Goal: run AIRP in the target Azure environment.

Tasks:

- [ ] Provision production PostgreSQL with pgvector.
- [ ] Provision Redis.
- [ ] Provision Temporal service or cluster.
- [ ] Provision Azure Event Hubs namespace and topics.
- [ ] Configure Event Hubs Kafka credentials.
- [ ] Configure Kubernetes secrets or external secret manager.
- [ ] Deploy AIRP API with Helm.
- [ ] Deploy AIRP Temporal worker.
- [ ] Deploy AIRP Event Hubs consumer.
- [ ] Configure ingress, TLS, DNS, and network policy.
- [ ] Configure workload identity where possible.
- [ ] Verify `/api/health`, readiness, and protected APIs.

Acceptance criteria:

- AIRP API runs in AKS with at least two replicas.
- Workers run and connect to Temporal/Event Hubs.
- Secrets are not stored in plain Helm values.

## Milestone 18: End-to-End Incident Simulation

Goal: prove the full product works against a realistic incident.

Tasks:

- [ ] Create synthetic alert payloads for high latency, crash loop, bad config, and failed deployment.
- [ ] Create a controlled test repo in AIRP-client.
- [ ] Ensure test repo builds public DockerHub image.
- [ ] Deploy test image to AKS.
- [ ] Trigger Prometheus/Alertmanager alert into Event Hubs.
- [ ] Verify incident creation.
- [ ] Verify Kubernetes evidence collection.
- [ ] Verify image-to-commit correlation.
- [ ] Verify GitHub issue creation.
- [ ] Verify Slack notification.
- [ ] Verify remediation plan and approval request.
- [ ] Verify approved draft PR creation.
- [ ] Verify documentation report and embedding.
- [ ] Record demo script and troubleshooting notes.

Acceptance criteria:

- A real alert completes the workflow from detection to issue, notification, approval, PR, and RCA documentation.
- Replay does not create duplicate issue, Slack thread, or PR.

## Milestone 19: Load, Resilience, and Chaos Testing

Goal: ensure the platform behaves well under production stress.

Tasks:

- [ ] Load test alert ingestion bursts.
- [ ] Load test API read paths.
- [ ] Test concurrent incidents across multiple services.
- [ ] Simulate Event Hubs outage.
- [ ] Simulate Temporal worker restart.
- [ ] Simulate GenAI Hub timeout/rate limit.
- [ ] Simulate Kubernetes MCP outage.
- [ ] Simulate GitHub MCP outage.
- [ ] Simulate Slack outage.
- [ ] Verify retries, dead-letter behavior, and escalation paths.

Acceptance criteria:

- No duplicate artifacts during retries.
- Failures leave visible audit trail and actionable escalation.

## Milestone 20: Documentation and Handoff

Goal: make the product operable by another engineer or SRE team.

Tasks:

- [ ] Complete architecture documentation.
- [ ] Complete API reference and authentication guide.
- [ ] Complete deployment guide with AKS-specific values.
- [ ] Complete Event Hubs setup guide.
- [ ] Complete MCP setup guides.
- [ ] Complete Slack app setup guide.
- [ ] Complete GenAI Hub configuration guide.
- [ ] Complete runbooks for incident replay, approval issues, key rotation, worker outage, and rollback.
- [ ] Add onboarding guide for a new AIRP-client service.
- [ ] Add production readiness checklist.

Acceptance criteria:

- A new engineer can deploy AIRP from the docs.
- A new service can be onboarded without code changes.

## Cross-Cutting Backlog

These tasks span multiple milestones:

- [ ] Add typed domain events for every state transition.
- [ ] Add event schema versioning and compatibility checks.
- [ ] Add idempotency key helper library.
- [ ] Add centralized policy engine for approval and remediation guardrails.
- [ ] Add feature flags for issue creation, Slack notification, PR creation, and documentation publishing.
- [ ] Add tenant/environment separation if multiple client environments are added.
- [ ] Add database backup and restore scripts.
- [ ] Add cleanup jobs for old Redis keys and stale workflow artifacts.
- [ ] Add cost dashboard for GenAI Hub usage.
- [ ] Add admin API for model routing and policy configuration.

## Suggested Immediate Next Sprint

Sprint goal: make a real alert create a durable incident.

Tasks:

1. Verify PostgreSQL migration with Docker Compose.
2. Add typed Kafka event contracts. Done.
3. Implement Alertmanager payload normalization. Done.
4. Implement Redis dedupe key storage. Done.
5. Implement Event Hubs consumer worker. Done.
6. Create incident from validated alert. Done.
7. Add tests for duplicate replay and malformed event dead-lettering. Done with service-level idempotency tests and dead-letter event tests; PostgreSQL verification remains in Milestone 1.
8. Document how to publish a sample alert event. Done with `scripts/publish-sample-alert.py`, README notes, and deployment guide notes.

Demo at end of sprint:

```text
sample Alertmanager event -> Azure Event Hubs Kafka topic -> AIRP consumer -> incident row -> audit event -> API lookup
```

## Definition of Production Ready

AIRP should be considered production-ready only when all of the following are true:

- Real AKS incident evidence is collected through Kubernetes MCP.
- Real AIRP-client repository evidence is collected through GitHub MCP.
- Real Slack notification and approval flow works.
- Real GitHub issue and draft PR creation works with idempotency.
- GenAI Hub agent outputs are structured, validated, redacted, and evidence-backed.
- PostgreSQL + pgvector incident memory is active.
- Temporal workflows survive worker restarts.
- Event Hubs replay does not create duplicate artifacts.
- Secrets are managed through Kubernetes Secrets or external secret manager.
- CI runs lint, tests, migration checks, image build, and Helm checks.
- Production deployment has monitoring, alerts, runbooks, rollback, and audit export.

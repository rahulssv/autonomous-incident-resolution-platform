from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

from airp.domain.enums import IncidentStatus

ACTIVITY_TIMEOUT = timedelta(seconds=30)
EXTERNAL_ACTION_ACTIVITY_TIMEOUT = timedelta(seconds=90)
ACTIVITY_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=5,
)
AGENT_GRAPH_ACTIVITY_TIMEOUT = timedelta(minutes=8)
AGENT_GRAPH_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    maximum_interval=timedelta(seconds=20),
    maximum_attempts=3,
)


@dataclass
class IncidentWorkflowInput:
    incident_id: str
    severity: str
    correlation_id: str | None = None
    source: str = "alert-ingestion"


@dataclass
class IncidentWorkflowState:
    incident_id: str
    status: str
    current_step: str
    severity: str
    correlation_id: str | None = None
    paused: bool = False
    completed: bool = False
    last_signal: str | None = None
    signal_history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class WorkflowSignal:
    name: str
    reason: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@workflow.defn
class IncidentWorkflow:
    def __init__(self) -> None:
        self.state: IncidentWorkflowState | None = None
        self._signals: list[WorkflowSignal] = []

    @workflow.run
    async def run(self, payload: IncidentWorkflowInput) -> IncidentWorkflowState:
        self.state = IncidentWorkflowState(
            incident_id=payload.incident_id,
            status=IncidentStatus.RECEIVED.value,
            current_step="received",
            severity=payload.severity,
            correlation_id=payload.correlation_id,
        )
        await self._update_status(
            IncidentStatus.VALIDATED.value,
            reason="Incident workflow started from validated alert.",
            payload={"source": payload.source},
        )
        self.state.status = IncidentStatus.VALIDATED.value
        self.state.current_step = "validated"
        await self._run_agent_graph()
        self.state.current_step = "rca_hypotheses_generated"
        await self._record_workflow_event(
            "workflow.step.completed",
            {"step": "rca_hypotheses_generated"},
        )
        github_result = await self._create_github_issue()
        self.state.current_step = f"github_issue_{github_result.get('status', 'unknown')}"
        if github_result.get("status") == "created":
            self.state.status = IncidentStatus.RCA_ISSUE_CREATED.value
            await self._update_status(
                IncidentStatus.RCA_ISSUE_CREATED.value,
                "GitHub issue was created for the RCA.",
                {
                    "issue_url": github_result.get("issue_url"),
                    "repository_url": github_result.get("repository_url"),
                    "existing": github_result.get("existing"),
                },
            )
            await self._record_workflow_event(
                "workflow.step.completed",
                {"step": "github_issue_created"},
            )

        slack_result = await self._send_slack_notification()
        self.state.current_step = f"slack_notification_{slack_result.get('status', 'unknown')}"
        if slack_result.get("status") == "sent":
            self.state.status = IncidentStatus.SLACK_NOTIFIED.value
            await self._update_status(
                IncidentStatus.SLACK_NOTIFIED.value,
                "Slack notification was sent for the RCA.",
                {
                    "channel": slack_result.get("channel"),
                    "slack_message_id": slack_result.get("slack_message_id"),
                },
            )
            await self._record_workflow_event(
                "workflow.step.completed",
                {"step": "slack_notification_sent"},
            )

        remediation_pr_result = await self._create_remediation_pr()
        self.state.current_step = (
            f"remediation_pr_{remediation_pr_result.get('status', 'unknown')}"
        )
        if remediation_pr_result.get("status") == "created":
            self.state.status = IncidentStatus.PR_CREATED.value
            await self._update_status(
                IncidentStatus.PR_CREATED.value,
                "Remediation pull request was created for the RCA.",
                {
                    "pull_request_url": remediation_pr_result.get("pull_request_url"),
                    "repository_url": remediation_pr_result.get("repository_url"),
                    "branch": remediation_pr_result.get("branch"),
                    "assignee": remediation_pr_result.get("assignee"),
                    "existing": remediation_pr_result.get("existing"),
                },
            )
            await self._record_workflow_event(
                "workflow.step.completed",
                {"step": "remediation_pr_created"},
            )

        while not self.state.completed:
            await workflow.wait_condition(lambda: bool(self._signals))
            signal = self._signals.pop(0)
            await self._handle_signal(signal)

        return self.state

    @workflow.query
    def current_state(self) -> IncidentWorkflowState | None:
        return self.state

    @workflow.signal
    async def pause(self, reason: str | None = None, payload: dict[str, Any] | None = None) -> None:
        self._signals.append(WorkflowSignal("pause", reason, payload or {}))

    @workflow.signal
    async def resume(
        self, reason: str | None = None, payload: dict[str, Any] | None = None
    ) -> None:
        self._signals.append(WorkflowSignal("resume", reason, payload or {}))

    @workflow.signal
    async def approve(
        self, reason: str | None = None, payload: dict[str, Any] | None = None
    ) -> None:
        self._signals.append(WorkflowSignal("approve", reason, payload or {}))

    @workflow.signal
    async def reject(
        self, reason: str | None = None, payload: dict[str, Any] | None = None
    ) -> None:
        self._signals.append(WorkflowSignal("reject", reason, payload or {}))

    @workflow.signal
    async def escalate(
        self, reason: str | None = None, payload: dict[str, Any] | None = None
    ) -> None:
        self._signals.append(WorkflowSignal("escalate", reason, payload or {}))

    @workflow.signal
    async def close(self, reason: str | None = None, payload: dict[str, Any] | None = None) -> None:
        self._signals.append(WorkflowSignal("close", reason, payload or {}))

    async def _handle_signal(self, signal: WorkflowSignal) -> None:
        if self.state is None:
            return

        self.state.last_signal = signal.name
        self.state.signal_history.append(
            {
                "signal": signal.name,
                "reason": signal.reason,
                "payload": signal.payload,
            }
        )

        if signal.name == "pause":
            self.state.paused = True
            self.state.current_step = "paused"
            await self._record_signal(signal)
            return

        if signal.name == "resume":
            self.state.paused = False
            self.state.current_step = "validated"
            await self._record_signal(signal)
            return

        if signal.name == "approve":
            self.state.status = IncidentStatus.APPROVED.value
            self.state.current_step = "approved"
            await self._update_status(IncidentStatus.APPROVED.value, signal.reason, signal.payload)
            return

        if signal.name == "reject":
            self.state.status = IncidentStatus.ESCALATED.value
            self.state.current_step = "rejected"
            self.state.completed = True
            await self._update_status(IncidentStatus.ESCALATED.value, signal.reason, signal.payload)
            return

        if signal.name == "escalate":
            self.state.status = IncidentStatus.ESCALATED.value
            self.state.current_step = "escalated"
            self.state.completed = True
            await self._update_status(IncidentStatus.ESCALATED.value, signal.reason, signal.payload)
            return

        if signal.name == "close":
            self.state.status = IncidentStatus.CLOSED.value
            self.state.current_step = "closed"
            self.state.completed = True
            await self._update_status(IncidentStatus.CLOSED.value, signal.reason, signal.payload)

    async def _update_status(
        self,
        status: str,
        reason: str | None,
        payload: dict[str, Any],
    ) -> None:
        if self.state is None:
            return
        await workflow.execute_activity(
            "incident_update_status",
            args=[
                self.state.incident_id,
                status,
                reason,
                payload,
            ],
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

    async def _record_signal(self, signal: WorkflowSignal) -> None:
        if self.state is None:
            return
        await self._record_workflow_event(
            "workflow.signaled",
            {
                "signal": signal.name,
                "reason": signal.reason,
                "payload": signal.payload,
            },
        )

    async def _record_workflow_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.state is None:
            return
        await workflow.execute_activity(
            "incident_record_workflow_event",
            args=[self.state.incident_id, event_type, payload],
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

    async def _run_agent_graph(self) -> None:
        if self.state is None:
            return
        await workflow.execute_activity(
            "agent_graph_run",
            args=[self.state.incident_id, workflow.info().workflow_id],
            start_to_close_timeout=AGENT_GRAPH_ACTIVITY_TIMEOUT,
            retry_policy=AGENT_GRAPH_RETRY_POLICY,
        )

    async def _create_github_issue(self) -> dict[str, Any]:
        if self.state is None:
            return {"status": "skipped", "reason": "workflow state is unavailable"}
        result = await workflow.execute_activity(
            "incident_create_github_issue",
            args=[self.state.incident_id],
            start_to_close_timeout=EXTERNAL_ACTION_ACTIVITY_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        return dict(result or {})

    async def _send_slack_notification(self) -> dict[str, Any]:
        if self.state is None:
            return {"status": "skipped", "reason": "workflow state is unavailable"}
        result = await workflow.execute_activity(
            "incident_send_slack_notification",
            args=[self.state.incident_id],
            start_to_close_timeout=EXTERNAL_ACTION_ACTIVITY_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        return dict(result or {})

    async def _create_remediation_pr(self) -> dict[str, Any]:
        if self.state is None:
            return {"status": "skipped", "reason": "workflow state is unavailable"}
        result = await workflow.execute_activity(
            "incident_create_remediation_pr",
            args=[self.state.incident_id],
            start_to_close_timeout=EXTERNAL_ACTION_ACTIVITY_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        return dict(result or {})

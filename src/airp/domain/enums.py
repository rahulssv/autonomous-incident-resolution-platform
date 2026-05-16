from enum import StrEnum


class IncidentSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class IncidentStatus(StrEnum):
    RECEIVED = "received"
    VALIDATED = "validated"
    CORRELATED = "correlated"
    RCA_COLLECTING_K8S_EVIDENCE = "rca_collecting_k8s_evidence"
    IMAGE_CORRELATED = "image_correlated"
    RCA_COLLECTING_GITHUB_EVIDENCE = "rca_collecting_github_evidence"
    RCA_IN_PROGRESS = "rca_in_progress"
    RCA_ISSUE_CREATED = "rca_issue_created"
    SLACK_NOTIFIED = "slack_notified"
    REMEDIATION_PLANNED = "remediation_planned"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    APPROVED = "approved"
    PR_CREATED = "pr_created"
    CI_VALIDATING = "ci_validating"
    DOCUMENTING = "documenting"
    CLOSED = "closed"
    ESCALATED = "escalated"


class RemediationStatus(StrEnum):
    PROPOSED = "proposed"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    PR_CREATED = "pr_created"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

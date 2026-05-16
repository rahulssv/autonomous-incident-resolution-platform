from __future__ import annotations

from dataclasses import dataclass

from airp.core.config import Settings, get_settings


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


class ExternalActionPolicy:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def github_issue_creation(self) -> PolicyDecision:
        if not self.settings.github_issue_creation_enabled:
            return PolicyDecision(False, "GitHub issue creation feature flag is disabled")
        return PolicyDecision(True, "GitHub issue creation feature flag is enabled")

    def slack_notification(self) -> PolicyDecision:
        if not self.settings.slack_notifications_enabled:
            return PolicyDecision(False, "Slack notification feature flag is disabled")
        return PolicyDecision(True, "Slack notification feature flag is enabled")

    def remediation_pr_creation(self) -> PolicyDecision:
        if not self.settings.remediation_pr_creation_enabled:
            return PolicyDecision(False, "Remediation PR creation feature flag is disabled")
        return PolicyDecision(True, "Remediation PR creation feature flag is enabled")

    def documentation_publishing(self) -> PolicyDecision:
        if not self.settings.documentation_publishing_enabled:
            return PolicyDecision(False, "Documentation publishing feature flag is disabled")
        return PolicyDecision(True, "Documentation publishing feature flag is enabled")

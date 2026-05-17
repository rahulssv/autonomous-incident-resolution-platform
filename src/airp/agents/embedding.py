from __future__ import annotations

import time
from typing import Protocol

from airp.agents.state import AgentEvent, AgentGraphState, EmbeddingRun
from airp.core.config import Settings, get_settings
from airp.integrations.genaihub.redaction import redact_text


class EmbeddingClient(Protocol):
    def embed(self, *, input_text: str | list[str], model: str | None = None) -> list[list[float]]:
        """Return embedding vectors for the provided text."""


_EMBEDDING_RATE_LIMITED_UNTIL = 0.0


class EmbeddingAgent:
    name = "embedding"

    def __init__(
        self,
        settings: Settings | None = None,
        embedder: EmbeddingClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.embedder = embedder

    async def __call__(self, state: AgentGraphState) -> AgentGraphState:
        if not self.settings.embedding_enabled:
            run = EmbeddingRun(
                embedded_text_count=0,
                vector_count=0,
                skipped=True,
                reason="Embedding generation is disabled.",
            )
            return self._state_update(state, run, [], [])

        texts = self._texts_from_state(state)
        if not texts:
            run = EmbeddingRun(
                embedded_text_count=0,
                vector_count=0,
                skipped=True,
                reason="No incident text was available for embedding.",
            )
            return self._state_update(state, run, [], [])

        redacted_texts = self._budget_texts([redact_text(text) for text in texts])
        if not redacted_texts:
            run = EmbeddingRun(
                embedded_text_count=0,
                vector_count=0,
                skipped=True,
                reason="No incident text remained after embedding budget limits.",
            )
            return self._state_update(state, run, [], [])

        if self.embedder is None:
            run = EmbeddingRun(
                embedded_text_count=len(redacted_texts),
                vector_count=0,
                skipped=True,
                reason="Embedding client is not configured.",
            )
            return self._state_update(state, run, redacted_texts, [])

        cooldown_remaining = self._rate_limit_cooldown_remaining()
        if cooldown_remaining > 0:
            run = EmbeddingRun(
                embedded_text_count=len(redacted_texts),
                vector_count=0,
                skipped=True,
                reason=(
                    "Embedding generation skipped because the LLM gateway recently returned a "
                    f"rate limit response. Cooldown remaining: {cooldown_remaining:.0f}s."
                ),
            )
            return self._state_update(state, run, redacted_texts, [])

        try:
            vectors = self.embedder.embed(
                input_text=redacted_texts,
                model=self.settings.llm_embedding_model,
            )
        except Exception as exc:  # noqa: BLE001 - embedding must not fail incident persistence
            if _is_rate_limit_error(exc):
                self._start_rate_limit_cooldown()
            run = EmbeddingRun(
                embedded_text_count=len(redacted_texts),
                vector_count=0,
                skipped=True,
                reason=f"Embedding generation failed: {exc}",
            )
            return self._state_update(state, run, redacted_texts, [])
        run = EmbeddingRun(
            embedded_text_count=len(redacted_texts),
            vector_count=len(vectors),
            skipped=False,
        )
        return self._state_update(state, run, redacted_texts, vectors)

    def _texts_from_state(self, state: AgentGraphState) -> list[str]:
        texts: list[str] = []
        self._append_text(texts, state.get("title"))
        self._append_text(texts, state.get("description"))
        if state.get("monitoring_assessment"):
            self._append_text(texts, state["monitoring_assessment"].get("summary"))
        if state.get("correlation_result"):
            self._append_text(texts, state["correlation_result"].get("context_summary"))
        if state.get("rca_plan"):
            self._append_text(texts, state["rca_plan"].get("summary"))
        if state.get("remediation_result"):
            remediation = state["remediation_result"]
            self._append_text(texts, remediation.get("plan_summary"))
            self._append_text(texts, remediation.get("test_plan"))
            self._append_text(texts, remediation.get("rollback_plan"))
            self._append_joined(
                texts,
                "Remediation actions",
                remediation.get("recommended_actions"),
            )
        if state.get("documentation_report"):
            report = state["documentation_report"]
            self._append_text(texts, report.get("executive_summary"))
            self._append_text(texts, report.get("root_cause_summary"))
            self._append_text(texts, report.get("evidence_summary"))
            self._append_text(texts, report.get("remediation_summary"))
            self._append_joined(texts, "Documentation follow-ups", report.get("follow_up_tasks"))
        return texts

    def _append_text(self, texts: list[str], value: object) -> None:
        if value:
            texts.append(str(value))

    def _append_joined(self, texts: list[str], label: str, value: object) -> None:
        if isinstance(value, list) and value:
            texts.append(f"{label}: {', '.join(str(item) for item in value)}")

    def _budget_texts(self, texts: list[str]) -> list[str]:
        max_texts = self.settings.embedding_max_texts
        per_text_limit = self.settings.embedding_text_max_chars
        total_limit = self.settings.embedding_total_max_chars
        budgeted: list[str] = []
        seen: set[str] = set()
        used_chars = 0

        for raw_text in texts:
            text = " ".join(str(raw_text).split())
            if not text:
                continue
            if len(text) > per_text_limit:
                text = text[:per_text_limit].rstrip()
            remaining = total_limit - used_chars
            if remaining <= 0 or len(budgeted) >= max_texts:
                break
            if len(text) > remaining:
                text = text[:remaining].rstrip()
            if not text or text in seen:
                continue
            budgeted.append(text)
            seen.add(text)
            used_chars += len(text)
        return budgeted

    def _rate_limit_cooldown_remaining(self) -> float:
        if self.settings.embedding_rate_limit_cooldown_seconds <= 0:
            return 0.0
        return max(0.0, _EMBEDDING_RATE_LIMITED_UNTIL - time.monotonic())

    def _start_rate_limit_cooldown(self) -> None:
        global _EMBEDDING_RATE_LIMITED_UNTIL
        cooldown = self.settings.embedding_rate_limit_cooldown_seconds
        _EMBEDDING_RATE_LIMITED_UNTIL = time.monotonic() + cooldown if cooldown > 0 else 0.0

    def _state_update(
        self,
        state: AgentGraphState,
        run: EmbeddingRun,
        texts: list[str],
        vectors: list[list[float]],
    ) -> AgentGraphState:
        event = AgentEvent(
            event_type="embedding.generated" if not run.skipped else "embedding.skipped",
            agent=self.name,
            payload=run.model_dump(mode="json"),
        )
        return {
            "embedding_run": run.model_dump(mode="json"),
            "embedding_texts": texts,
            "embedding_vectors": vectors,
            "agent_events": [event.model_dump(mode="json")],
        }


def _is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "429" in message
        or "rate limit" in message
        or "ratelimit" in message
        or "tpm limit" in message
        or "too many requests" in message
    )

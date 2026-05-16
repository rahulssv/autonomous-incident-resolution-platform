from __future__ import annotations

from typing import Protocol

from airp.agents.state import AgentEvent, AgentGraphState, EmbeddingRun
from airp.core.config import Settings, get_settings
from airp.integrations.genaihub.redaction import redact_text


class EmbeddingClient(Protocol):
    def embed(self, *, input_text: str | list[str], model: str | None = None) -> list[list[float]]:
        """Return embedding vectors for the provided text."""


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
        texts = self._texts_from_state(state)
        if not texts:
            run = EmbeddingRun(
                embedded_text_count=0,
                vector_count=0,
                skipped=True,
                reason="No incident text was available for embedding.",
            )
            return self._state_update(state, run, [], [])

        redacted_texts = [redact_text(text) for text in texts]
        if self.embedder is None:
            run = EmbeddingRun(
                embedded_text_count=len(redacted_texts),
                vector_count=0,
                skipped=True,
                reason="Embedding client is not configured.",
            )
            return self._state_update(state, run, redacted_texts, [])

        vectors = self.embedder.embed(
            input_text=redacted_texts,
            model=self.settings.llm_embedding_model,
        )
        run = EmbeddingRun(
            embedded_text_count=len(redacted_texts),
            vector_count=len(vectors),
            skipped=False,
        )
        return self._state_update(state, run, redacted_texts, vectors)

    def _texts_from_state(self, state: AgentGraphState) -> list[str]:
        texts: list[str] = []
        if state.get("title"):
            texts.append(str(state["title"]))
        if state.get("description"):
            texts.append(str(state["description"]))
        if state.get("monitoring_assessment"):
            summary = state["monitoring_assessment"].get("summary")
            if summary:
                texts.append(str(summary))
        return texts

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
            "agent_events": [*state.get("agent_events", []), event.model_dump(mode="json")],
        }

from __future__ import annotations

from airp.agents.embedding import EmbeddingAgent
from airp.agents.monitoring import MonitoringAgent
from airp.agents.supervisor import LangGraphSupervisor
from airp.core.config import Settings, get_settings
from airp.integrations.genaihub.client import GenAIHubClient


def build_default_agent_supervisor(settings: Settings | None = None) -> LangGraphSupervisor:
    settings = settings or get_settings()
    genai_client = None
    if settings.gateway_base_url and settings.gateway_api_key:
        genai_client = GenAIHubClient(settings)

    return LangGraphSupervisor(
        monitoring_agent=MonitoringAgent(settings=settings, llm_client=genai_client),
        embedding_agent=EmbeddingAgent(settings=settings, embedder=genai_client),
    )

from __future__ import annotations

from airp.agents.factory import build_default_agent_supervisor
from airp.core.config import Settings
from airp.integrations.genaihub.client import (
    AnthropicGatewayClient,
    GenAIHubClient,
    _anthropic_openai_base_url,
)


def test_agent_factory_prefers_anthropic_gateway_when_configured() -> None:
    supervisor = build_default_agent_supervisor(
        Settings(
            _env_file=None,
            anthropic_base_url="https://anthropic.example.test/v1",
            anthropic_auth_token="test-token",
            gateway_base_url="https://gateway.example.test",
            gateway_api_key="legacy-token",
        )
    )

    assert isinstance(supervisor.monitoring_agent.llm_client, AnthropicGatewayClient)
    assert supervisor.rca_agent.llm_client is supervisor.monitoring_agent.llm_client
    # Anthropic-style gateways do not expose /v1/embeddings, so the embedder must
    # route to the GenAI Hub gateway when it is also configured.
    assert isinstance(supervisor.embedding_agent.embedder, GenAIHubClient)


def test_agent_factory_uses_anthropic_for_embeddings_when_genaihub_not_configured() -> None:
    supervisor = build_default_agent_supervisor(
        Settings(
            _env_file=None,
            anthropic_base_url="https://anthropic.example.test/v1",
            anthropic_auth_token="test-token",
        )
    )

    assert isinstance(supervisor.monitoring_agent.llm_client, AnthropicGatewayClient)
    assert supervisor.embedding_agent.embedder is supervisor.monitoring_agent.llm_client


def test_agent_factory_falls_back_to_genaihub_gateway() -> None:
    supervisor = build_default_agent_supervisor(
        Settings(
            _env_file=None,
            gateway_base_url="https://gateway.example.test",
            gateway_api_key="legacy-token",
        )
    )

    assert isinstance(supervisor.monitoring_agent.llm_client, GenAIHubClient)


def test_anthropic_gateway_normalizes_openai_v1_base_url() -> None:
    assert (
        _anthropic_openai_base_url("https://anthropic.example.test/v1/inferencing-server")
        == "https://anthropic.example.test/v1/inferencing-server/v1"
    )
    assert (
        _anthropic_openai_base_url("https://anthropic.example.test/v1/inferencing-server/v1")
        == "https://anthropic.example.test/v1/inferencing-server/v1"
    )

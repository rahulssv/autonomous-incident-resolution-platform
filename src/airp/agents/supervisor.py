from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from airp.agents.embedding import EmbeddingAgent
from airp.agents.monitoring import MonitoringAgent
from airp.agents.state import AgentGraphState


class LangGraphSupervisor:
    def __init__(
        self,
        monitoring_agent: MonitoringAgent | None = None,
        embedding_agent: EmbeddingAgent | None = None,
    ) -> None:
        self.monitoring_agent = monitoring_agent or MonitoringAgent()
        self.embedding_agent = embedding_agent or EmbeddingAgent()
        self.graph = self._build_graph()

    async def run(
        self,
        *,
        incident_id: str,
        title: str,
        severity: str,
        status: str,
        description: str | None = None,
        workflow_id: str | None = None,
        correlation_id: str | None = None,
    ) -> AgentGraphState:
        initial_state: AgentGraphState = {
            "incident_id": incident_id,
            "workflow_id": workflow_id,
            "title": title,
            "description": description,
            "severity": severity,
            "status": status,
            "correlation_id": correlation_id,
            "agent_events": [],
            "evidence_ids": [],
            "errors": [],
        }
        return await self.graph.ainvoke(initial_state)

    def _build_graph(self):
        graph = StateGraph(AgentGraphState)
        graph.add_node("monitoring", self.monitoring_agent)
        graph.add_node("embedding", self.embedding_agent)
        graph.add_edge(START, "monitoring")
        graph.add_edge("monitoring", "embedding")
        graph.add_edge("embedding", END)
        return graph.compile()

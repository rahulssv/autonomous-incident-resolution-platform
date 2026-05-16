from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from airp.agents.correlation import CorrelationAgent
from airp.agents.documentation import DocumentationAgent
from airp.agents.embedding import EmbeddingAgent
from airp.agents.monitoring import MonitoringAgent
from airp.agents.rca import RCAAgent
from airp.agents.remediation import RemediationAgent
from airp.agents.state import AgentGraphState


class LangGraphSupervisor:
    def __init__(
        self,
        monitoring_agent: MonitoringAgent | None = None,
        correlation_agent: CorrelationAgent | None = None,
        rca_agent: RCAAgent | None = None,
        remediation_agent: RemediationAgent | None = None,
        documentation_agent: DocumentationAgent | None = None,
        embedding_agent: EmbeddingAgent | None = None,
    ) -> None:
        self.monitoring_agent = monitoring_agent or MonitoringAgent()
        self.correlation_agent = correlation_agent or CorrelationAgent()
        self.rca_agent = rca_agent or RCAAgent()
        self.remediation_agent = remediation_agent or RemediationAgent()
        self.documentation_agent = documentation_agent or DocumentationAgent()
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
        service_context: dict | None = None,
        workload_context: dict | None = None,
    ) -> AgentGraphState:
        initial_state: AgentGraphState = {
            "incident_id": incident_id,
            "workflow_id": workflow_id,
            "title": title,
            "description": description,
            "severity": severity,
            "status": status,
            "correlation_id": correlation_id,
            "service_context": service_context or {},
            "workload_context": workload_context or {},
            "agent_events": [],
            "evidence_ids": [],
            "errors": [],
        }
        return await self.graph.ainvoke(initial_state)

    def _build_graph(self):
        graph = StateGraph(AgentGraphState)
        graph.add_node("monitoring", self.monitoring_agent)
        graph.add_node("correlation", self.correlation_agent)
        graph.add_node("rca", self.rca_agent)
        graph.add_node("remediation", self.remediation_agent)
        graph.add_node("documentation", self.documentation_agent)
        graph.add_node("embedding", self.embedding_agent)
        graph.add_edge(START, "monitoring")
        graph.add_edge("monitoring", "correlation")
        graph.add_edge("correlation", "rca")
        graph.add_edge("rca", "remediation")
        graph.add_edge("remediation", "documentation")
        graph.add_edge("documentation", "embedding")
        graph.add_edge("embedding", END)
        return graph.compile()

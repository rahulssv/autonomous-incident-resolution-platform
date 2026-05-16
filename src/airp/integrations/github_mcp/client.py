from typing import Any


class GitHubMCPClient:
    """Thin boundary for future MCP transport implementation."""

    async def list_org_repositories(self, org: str) -> list[dict[str, Any]]:
        raise NotImplementedError("GitHub MCP transport will be implemented in the workflow phase")

    async def create_issue(self, repository: str, title: str, body: str) -> dict[str, Any]:
        raise NotImplementedError("GitHub MCP transport will be implemented in the workflow phase")

    async def create_pull_request(self, repository: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("GitHub MCP transport will be implemented in the workflow phase")

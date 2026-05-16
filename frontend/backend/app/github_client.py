from __future__ import annotations

from typing import Any

import httpx

from .config import Settings
from .http_client import httpx_client_kwargs


class GitHubAPIError(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
        details: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.details = details
        self.headers = headers or {}
        super().__init__(message)


class GitHubClient:
    def __init__(self, settings: Settings, token: str | None = None) -> None:
        self.settings = settings
        self.token = token

    @property
    def headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self.settings.github_api_version,
            "User-Agent": "air-platform-dashboard",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token:
            raise GitHubAPIError(
                401,
                "GitHub token is required for GraphQL requests. Set GITHUB_TOKEN or pass an Authorization bearer token.",
            )

        payload = {"query": query, "variables": variables or {}}
        async with httpx.AsyncClient(**httpx_client_kwargs()) as client:
            response = await client.post(
                self.settings.github_graphql_url,
                headers=self.headers,
                json=payload,
            )

        data = self._decode_json(response)
        if response.is_error:
            raise GitHubAPIError(
                response.status_code,
                "GitHub GraphQL request failed.",
                data,
                dict(response.headers),
            )
        if data.get("errors"):
            raise GitHubAPIError(502, "GitHub GraphQL returned errors.", data["errors"])
        return data.get("data", {})

    async def rest(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = path if path.startswith("http") else f"{self.settings.github_base_url}{path}"
        async with httpx.AsyncClient(**httpx_client_kwargs()) as client:
            response = await client.request(
                method,
                url,
                headers=self.headers,
                params=params,
                json=json,
            )

        data = self._decode_json(response)
        if response.is_error:
            raise GitHubAPIError(
                response.status_code,
                "GitHub REST request failed.",
                data,
                dict(response.headers),
            )
        return data

    @staticmethod
    def _decode_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {"text": response.text}

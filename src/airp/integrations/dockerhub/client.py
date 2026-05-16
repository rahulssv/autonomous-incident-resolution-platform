from urllib.parse import quote

import httpx


class DockerHubClient:
    """Read-only client for public DockerHub image metadata."""

    def __init__(self, base_url: str = "https://hub.docker.com/v2") -> None:
        self.base_url = base_url.rstrip("/")

    async def get_tag(self, repository: str, tag: str) -> dict:
        encoded_repo = quote(repository, safe="/")
        url = f"{self.base_url}/repositories/{encoded_repo}/tags/{quote(tag, safe='')}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

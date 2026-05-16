from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field


class DockerImageReference(BaseModel):
    original: str
    repository: str
    tag: str | None = None
    digest: str | None = None


class DockerHubImageEvidence(BaseModel):
    image: str
    repository: str
    tag: str | None = None
    digest: str | None = None
    source_commit_sha: str | None = None
    last_updated: str | None = None
    status: str = "resolved"
    raw: dict[str, Any] = Field(default_factory=dict)


class DockerHubClient:
    """Read-only client for public DockerHub image metadata."""

    def __init__(
        self,
        base_url: str = "https://hub.docker.com/v2",
        fixture: dict[str, DockerHubImageEvidence | dict[str, Any]] | None = None,
        *,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.fixture = {
            key: DockerHubImageEvidence.model_validate(value)
            for key, value in (fixture or {}).items()
        }

    async def get_tag(self, repository: str, tag: str) -> dict:
        encoded_repo = quote(repository, safe="/")
        url = f"{self.base_url}/repositories/{encoded_repo}/tags/{quote(tag, safe='')}"
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def get_image_evidence(self, image: str) -> DockerHubImageEvidence:
        reference = parse_image_reference(image)
        fixture = self._fixture_for(reference)
        if fixture is not None:
            return fixture

        if reference.tag is None:
            return DockerHubImageEvidence(
                image=image,
                repository=reference.repository,
                digest=reference.digest,
                status="unresolved_without_tag",
            )

        payload = await self.get_tag(reference.repository, reference.tag)
        digest = reference.digest or payload.get("digest")
        source_commit_sha = _source_commit_from_payload(payload)
        return DockerHubImageEvidence(
            image=image,
            repository=reference.repository,
            tag=reference.tag,
            digest=digest,
            source_commit_sha=source_commit_sha,
            last_updated=payload.get("last_updated"),
            raw=payload,
        )

    def _fixture_for(self, reference: DockerImageReference) -> DockerHubImageEvidence | None:
        keys = [
            reference.original,
            f"{reference.repository}:{reference.tag}" if reference.tag else None,
            f"{reference.repository}@{reference.digest}" if reference.digest else None,
            reference.repository,
        ]
        for key in keys:
            if key and key in self.fixture:
                return self.fixture[key]
        return None


def parse_image_reference(image: str) -> DockerImageReference:
    base, digest = _split_digest(image)
    base, tag = _split_tag(base)
    parts = [part for part in base.split("/") if part]
    if not parts:
        raise ValueError("Docker image reference must not be empty")

    if len(parts) == 1:
        repository = f"library/{parts[0]}"
    else:
        first = parts[0]
        if "." in first or ":" in first or first == "localhost":
            parts = parts[1:]
        repository = "/".join(parts)
        if "/" not in repository:
            repository = f"library/{repository}"

    return DockerImageReference(
        original=image,
        repository=repository,
        tag=tag,
        digest=digest,
    )


def _split_digest(image: str) -> tuple[str, str | None]:
    if "@" not in image:
        return image, None
    base, digest = image.rsplit("@", 1)
    return base, digest


def _split_tag(image: str) -> tuple[str, str | None]:
    last_slash = image.rfind("/")
    last_colon = image.rfind(":")
    if last_colon > last_slash:
        return image[:last_colon], image[last_colon + 1 :]
    return image, None


def _source_commit_from_payload(payload: dict[str, Any]) -> str | None:
    candidates = [
        payload.get("source_commit_sha"),
        payload.get("commit"),
        payload.get("images", [{}])[0].get("source_commit_sha")
        if payload.get("images")
        else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate
    return None

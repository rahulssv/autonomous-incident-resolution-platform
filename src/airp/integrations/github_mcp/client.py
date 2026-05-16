from __future__ import annotations

from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from airp.integrations.mcp_http import call_mcp_tool, item_list, optional_dict


class GitHubChangedFileEvidence(BaseModel):
    path: str
    status: str | None = None
    additions: int | None = None
    deletions: int | None = None
    patch_excerpt: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class GitHubCommitEvidence(BaseModel):
    sha: str
    message: str | None = None
    author: str | None = None
    authored_at: str | None = None
    url: str | None = None
    changed_files: list[GitHubChangedFileEvidence] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class GitHubPullRequestEvidence(BaseModel):
    number: int
    title: str
    url: str | None = None
    author: str | None = None
    merged_at: str | None = None
    merge_commit_sha: str | None = None
    changed_files: list[GitHubChangedFileEvidence] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class GitHubReleaseEvidence(BaseModel):
    tag_name: str
    name: str | None = None
    target_commitish: str | None = None
    published_at: str | None = None
    url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class GitHubIssueEvidence(BaseModel):
    number: int
    title: str
    url: str | None = None
    state: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    labels: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class GitHubEvidenceBundle(BaseModel):
    repository_url: str | None = None
    default_branch: str | None = None
    commits: list[GitHubCommitEvidence] = Field(default_factory=list)
    merged_prs: list[GitHubPullRequestEvidence] = Field(default_factory=list)
    changed_files: list[GitHubChangedFileEvidence] = Field(default_factory=list)
    releases: list[GitHubReleaseEvidence] = Field(default_factory=list)
    prior_issues: list[GitHubIssueEvidence] = Field(default_factory=list)
    collection_errors: list[str] = Field(default_factory=list)
    source_links: list[str] = Field(default_factory=list)


class GitHubMCPClient:
    """Thin boundary for future MCP transport implementation."""

    def __init__(
        self,
        fixture: GitHubEvidenceBundle | dict[str, Any] | None = None,
        *,
        transport: Literal["disabled", "mcp"] = "disabled",
        endpoint_url: str | None = None,
        timeout_seconds: float = 20.0,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.fixture = GitHubEvidenceBundle.model_validate(fixture) if fixture else None
        self.transport = transport
        self.endpoint_url = endpoint_url.rstrip("/") if endpoint_url else None
        self.timeout_seconds = timeout_seconds
        self.http_transport = http_transport

    async def list_org_repositories(self, org: str) -> list[dict[str, Any]]:
        if self.fixture and self.fixture.repository_url:
            owner, name = _repository_owner_name(self.fixture.repository_url)
            if owner and owner.lower() == org.lower():
                return [
                    {
                        "name": name,
                        "full_name": f"{owner}/{name}" if owner and name else name,
                        "html_url": self.fixture.repository_url,
                        "default_branch": self.fixture.default_branch,
                    }
                ]
            return []
        payload = await self._call_tool(
            "github.list_org_repositories",
            {"org": org},
        )
        return item_list(payload, "repositories", "items")

    async def get_repository(self, repository_url: str) -> dict[str, Any] | None:
        if self.fixture is not None:
            if self.fixture.repository_url and self.fixture.repository_url != repository_url:
                return None
            owner, name = _repository_owner_name(repository_url)
            return {
                "name": name,
                "owner": owner,
                "html_url": repository_url,
                "default_branch": self.fixture.default_branch,
            }
        payload = await self._call_tool(
            "github.get_repository",
            {"repository_url": repository_url},
        )
        return optional_dict(payload, "repository", "item")

    async def lookup_commits(
        self,
        repository_url: str,
        *,
        since: str | None = None,
        until: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if self.fixture is not None:
            if not self._matches_repository(repository_url):
                return []
            return [
                commit.model_dump(mode="json")
                for commit in self.fixture.commits[:limit]
            ]
        payload = await self._call_tool(
            "github.lookup_commits",
            {
                "repository_url": repository_url,
                "since": since,
                "until": until,
                "limit": limit,
            },
        )
        return item_list(payload, "commits", "items")

    async def lookup_commit(self, repository_url: str, sha: str) -> dict[str, Any] | None:
        if self.fixture is not None:
            if not self._matches_repository(repository_url):
                return None
            for commit in self.fixture.commits:
                if commit.sha == sha:
                    return commit.model_dump(mode="json")
            return None
        payload = await self._call_tool(
            "github.lookup_commit",
            {"repository_url": repository_url, "sha": sha},
        )
        return optional_dict(payload, "commit", "item")

    async def lookup_merged_prs(
        self,
        repository_url: str,
        *,
        since: str | None = None,
        until: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if self.fixture is not None:
            if not self._matches_repository(repository_url):
                return []
            return [
                pull_request.model_dump(mode="json")
                for pull_request in self.fixture.merged_prs[:limit]
            ]
        payload = await self._call_tool(
            "github.lookup_merged_prs",
            {
                "repository_url": repository_url,
                "since": since,
                "until": until,
                "limit": limit,
            },
        )
        return item_list(payload, "merged_prs", "pull_requests", "items")

    async def lookup_changed_files(
        self,
        repository_url: str,
        *,
        ref: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if self.fixture is not None:
            if not self._matches_repository(repository_url):
                return []
            return [
                changed_file.model_dump(mode="json")
                for changed_file in self._all_changed_files()[:limit]
            ]
        payload = await self._call_tool(
            "github.lookup_changed_files",
            {
                "repository_url": repository_url,
                "ref": ref,
                "since": since,
                "until": until,
                "limit": limit,
            },
        )
        return item_list(payload, "changed_files", "files", "items")

    async def lookup_releases(
        self,
        repository_url: str,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if self.fixture is not None:
            if not self._matches_repository(repository_url):
                return []
            return [
                release.model_dump(mode="json")
                for release in self.fixture.releases[:limit]
            ]
        payload = await self._call_tool(
            "github.lookup_releases",
            {"repository_url": repository_url, "limit": limit},
        )
        return item_list(payload, "releases", "items")

    async def lookup_prior_issues(
        self,
        repository_url: str,
        *,
        query: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if self.fixture is not None:
            if not self._matches_repository(repository_url):
                return []
            return [
                issue.model_dump(mode="json")
                for issue in self.fixture.prior_issues[:limit]
            ]
        payload = await self._call_tool(
            "github.lookup_prior_issues",
            {
                "repository_url": repository_url,
                "query": query,
                "limit": limit,
            },
        )
        return item_list(payload, "prior_issues", "issues", "items")

    async def lookup_branches(
        self,
        repository_url: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if self.fixture is not None:
            return []
        payload = await self._call_tool(
            "github.lookup_branches",
            {"repository_url": repository_url, "limit": limit},
        )
        return item_list(payload, "branches", "items")

    async def lookup_issue_by_idempotency_marker(
        self, repository_url: str, marker: str
    ) -> dict[str, Any] | None:
        issues = await self.lookup_prior_issues(repository_url, query=marker)
        for issue in issues:
            raw = issue.get("raw", {})
            if marker in issue.get("title", "") or marker in str(raw):
                return issue
        return None

    async def collect_evidence(
        self,
        *,
        repository_url: str | None,
        since: str | None = None,
        until: str | None = None,
    ) -> GitHubEvidenceBundle:
        if not repository_url:
            return GitHubEvidenceBundle(
                collection_errors=["repository_url is required for GitHub evidence collection"]
            )
        if self.fixture is not None:
            if not self._matches_repository(repository_url):
                return GitHubEvidenceBundle(
                    repository_url=repository_url,
                    collection_errors=["fixture does not match requested repository"],
                )
            changed_files = self._all_changed_files()
            return self.fixture.model_copy(update={"changed_files": changed_files})

        repository = await self.get_repository(repository_url)
        commits = [
            GitHubCommitEvidence.model_validate(commit)
            for commit in await self.lookup_commits(repository_url, since=since, until=until)
        ]
        merged_prs = [
            GitHubPullRequestEvidence.model_validate(pull_request)
            for pull_request in await self.lookup_merged_prs(
                repository_url, since=since, until=until
            )
        ]
        changed_files = [
            GitHubChangedFileEvidence.model_validate(changed_file)
            for changed_file in await self.lookup_changed_files(
                repository_url, since=since, until=until
            )
        ]
        releases = [
            GitHubReleaseEvidence.model_validate(release)
            for release in await self.lookup_releases(repository_url)
        ]
        prior_issues = [
            GitHubIssueEvidence.model_validate(issue)
            for issue in await self.lookup_prior_issues(repository_url)
        ]
        return GitHubEvidenceBundle(
            repository_url=repository_url,
            default_branch=repository.get("default_branch") if repository else None,
            commits=commits,
            merged_prs=merged_prs,
            changed_files=changed_files,
            releases=releases,
            prior_issues=prior_issues,
            source_links=_source_links(
                commits,
                merged_prs,
                changed_files,
                releases,
                prior_issues,
            ),
        )

    async def create_issue(self, repository: str, title: str, body: str) -> dict[str, Any]:
        _ = repository, title, body
        raise NotImplementedError(
            "GitHub issue creation remains disabled until approval and policy gates are implemented"
        )

    async def create_pull_request(self, repository: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ = repository, payload
        raise NotImplementedError(
            "GitHub pull request creation remains disabled until approval and "
            "policy gates are implemented"
        )

    def _matches_repository(self, repository_url: str) -> bool:
        return self.fixture is None or not self.fixture.repository_url or (
            self.fixture.repository_url.rstrip("/") == repository_url.rstrip("/")
        )

    def _all_changed_files(self) -> list[GitHubChangedFileEvidence]:
        if self.fixture is None:
            return []
        files = list(self.fixture.changed_files)
        for commit in self.fixture.commits:
            files.extend(commit.changed_files)
        for pull_request in self.fixture.merged_prs:
            files.extend(pull_request.changed_files)
        seen: set[str] = set()
        deduped: list[GitHubChangedFileEvidence] = []
        for changed_file in files:
            key = changed_file.path
            if key in seen:
                continue
            seen.add(key)
            deduped.append(changed_file)
        return deduped

    def _raise_unavailable(self) -> None:
        if self.transport == "disabled":
            raise NotImplementedError("GitHub MCP transport is disabled")
        if not self.endpoint_url:
            raise NotImplementedError("GitHub MCP endpoint URL is not configured")
        raise NotImplementedError(
            "Live GitHub MCP read transport is configured but not implemented yet"
        )

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if self.transport == "disabled":
            raise NotImplementedError("GitHub MCP transport is disabled")
        if not self.endpoint_url:
            raise NotImplementedError("GitHub MCP endpoint URL is not configured")
        return await call_mcp_tool(
            endpoint_url=self.endpoint_url,
            tool_name=tool_name,
            arguments=arguments,
            timeout_seconds=self.timeout_seconds,
            transport=self.http_transport,
        )


def _repository_owner_name(repository_url: str) -> tuple[str | None, str | None]:
    path = repository_url.rstrip("/").removesuffix(".git").split("github.com/")[-1]
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        return None, parts[0] if parts else None
    return parts[-2], parts[-1]


def _source_links(*values: Any) -> list[str]:
    links: list[str] = []
    for value in values:
        if isinstance(value, list):
            for item in value:
                links.extend(_source_links(item))
            continue
        raw = getattr(value, "raw", None)
        if isinstance(raw, dict):
            link = raw.get("source_link") or raw.get("url") or raw.get("html_url")
            if isinstance(link, str) and link:
                links.append(link)
    return list(dict.fromkeys(links))

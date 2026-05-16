from __future__ import annotations

import base64
import binascii
import os
import time
from typing import Any

import httpx
import jwt
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel):
    tool: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


SERVER_TYPE = os.getenv("AIRP_LOCAL_MCP_SERVER", "kubernetes")
app = FastAPI(title=f"AIRP Local {SERVER_TYPE.title()} MCP")
_GITHUB_TOKEN_CACHE: dict[str, Any] = {}


@app.get("/")
async def health() -> dict[str, str]:
    payload = {
        "service": f"airp-local-{SERVER_TYPE}-mcp",
        "status": "ok",
        "transport": "mcp-http-bridge",
    }
    if SERVER_TYPE == "github":
        payload["mode"] = "github_app" if _github_app_configured() else "fixture"
        payload["org"] = _github_default_org()
    return payload


@app.post("/tools/call")
async def call_tool(payload: ToolCallRequest) -> dict[str, Any]:
    if SERVER_TYPE == "kubernetes":
        return _kubernetes_tool(payload.tool, payload.arguments)
    if SERVER_TYPE == "github":
        return await _github_tool(payload.tool, payload.arguments)
    raise HTTPException(status_code=500, detail=f"Unsupported local MCP server: {SERVER_TYPE}")


def _kubernetes_tool(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    namespace = str(arguments.get("namespace") or "shopfast")
    pod_name = str(arguments.get("pod_name") or "checkout-api-local-7d9c")
    deployment = str(arguments.get("deployment") or "checkout-api")

    pods = [
        {
            "namespace": namespace,
            "name": pod_name,
            "phase": "Running",
            "ready": True,
            "restart_count": 0,
            "node_name": "local-kind-worker",
            "pod_ip": "10.244.0.42",
            "containers": ["checkout-api"],
            "images": ["docker.io/airp-client/checkout-api:local"],
            "labels": {"app": "checkout-api", "airp.local": "true"},
            "raw": {"source_link": f"local://kubernetes/{namespace}/pods/{pod_name}"},
        }
    ]
    events = [
        {
            "namespace": namespace,
            "reason": "Started",
            "message": f"Started local MCP fixture pod {pod_name}",
            "type": "Normal",
            "involved_object": pod_name,
            "timestamp": "2026-05-16T00:00:00Z",
            "raw": {"source_link": f"local://kubernetes/{namespace}/events/{pod_name}"},
        }
    ]
    deployment_payload = {
        "namespace": namespace,
        "name": deployment,
        "desired_replicas": 2,
        "ready_replicas": 2,
        "updated_replicas": 2,
        "available_replicas": 2,
        "images": ["docker.io/airp-client/checkout-api:local"],
        "labels": {"app": deployment},
        "raw": {"source_link": f"local://kubernetes/{namespace}/deployments/{deployment}"},
    }
    rollout_status = {
        "namespace": namespace,
        "deployment": deployment,
        "status": "healthy",
        "message": "Local MCP rollout fixture is healthy",
        "raw": {"source_link": f"local://kubernetes/{namespace}/rollouts/{deployment}"},
    }
    replica_sets = [
        {
            "namespace": namespace,
            "name": f"{deployment}-7d9c",
            "deployment": deployment,
            "desired_replicas": 2,
            "ready_replicas": 2,
            "images": ["docker.io/airp-client/checkout-api:local"],
            "raw": {"source_link": f"local://kubernetes/{namespace}/replicasets/{deployment}-7d9c"},
        }
    ]

    match tool:
        case "kubernetes.list_pods":
            return {"result": {"pods": pods}}
        case "kubernetes.get_pod":
            return {"result": {"pod": pods[0]}}
        case "kubernetes.get_pod_logs":
            return {
                "result": {
                    "lines": [
                        "INFO local MCP checkout-api fixture started",
                        "INFO readiness probe succeeded",
                        "INFO p95 latency steady at 42ms",
                    ]
                }
            }
        case "kubernetes.list_events":
            return {"result": {"events": events}}
        case "kubernetes.get_deployment":
            return {"result": {"deployment": deployment_payload}}
        case "kubernetes.get_rollout_status":
            return {"result": {"rollout_status": rollout_status}}
        case "kubernetes.list_replicasets":
            return {"result": {"replica_sets": replica_sets}}
        case _:
            raise HTTPException(status_code=404, detail=f"Unsupported Kubernetes MCP tool: {tool}")


async def _github_tool(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if _github_app_configured():
        return await _github_app_tool(tool, arguments)
    return _github_fixture_tool(tool, arguments)


def _github_fixture_tool(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    repository_url = str(
        arguments.get("repository_url") or "https://github.com/AIRP-client/checkout-api"
    )
    owner, name = _repository_owner_name(repository_url)
    repo = {
        "name": name,
        "owner": owner,
        "full_name": f"{owner}/{name}",
        "html_url": repository_url,
        "default_branch": "main",
    }
    changed_files = [
        {
            "path": "src/checkout/api.py",
            "status": "modified",
            "additions": 8,
            "deletions": 2,
            "patch_excerpt": "Local MCP fixture change summary",
            "raw": {"html_url": f"{repository_url}/blob/main/src/checkout/api.py"},
        }
    ]
    commits = [
        {
            "sha": "localmcp1234567890",
            "message": "Stabilize checkout latency",
            "author": "AIRP Local MCP",
            "authored_at": "2026-05-16T00:00:00Z",
            "url": f"{repository_url}/commit/localmcp1234567890",
            "changed_files": changed_files,
            "raw": {"html_url": f"{repository_url}/commit/localmcp1234567890"},
        }
    ]
    merged_prs = [
        {
            "number": 42,
            "title": "Improve checkout latency handling",
            "url": f"{repository_url}/pull/42",
            "author": "airp-local",
            "merged_at": "2026-05-16T00:00:00Z",
            "merge_commit_sha": "localmcp1234567890",
            "changed_files": changed_files,
            "raw": {"html_url": f"{repository_url}/pull/42"},
        }
    ]
    releases = [
        {
            "tag_name": "local-mcp-v1",
            "name": "Local MCP Fixture",
            "target_commitish": "main",
            "published_at": "2026-05-16T00:00:00Z",
            "url": f"{repository_url}/releases/tag/local-mcp-v1",
            "raw": {"html_url": f"{repository_url}/releases/tag/local-mcp-v1"},
        }
    ]
    issues = [
        {
            "number": 7,
            "title": "Local MCP prior checkout latency issue",
            "url": f"{repository_url}/issues/7",
            "state": "closed",
            "created_at": "2026-05-16T00:00:00Z",
            "updated_at": "2026-05-16T00:00:00Z",
            "labels": ["incident", "local-mcp"],
            "raw": {"html_url": f"{repository_url}/issues/7"},
        }
    ]

    match tool:
        case "github.list_org_repositories":
            org = str(arguments.get("org") or owner)
            return {"result": {"repositories": [repo] if org.lower() == owner.lower() else []}}
        case "github.get_repository":
            return {"result": {"repository": repo}}
        case "github.lookup_commits":
            return {"result": {"commits": commits}}
        case "github.lookup_commit":
            return {"result": {"commit": commits[0]}}
        case "github.lookup_merged_prs":
            return {"result": {"merged_prs": merged_prs}}
        case "github.lookup_changed_files":
            return {"result": {"changed_files": changed_files}}
        case "github.lookup_releases":
            return {"result": {"releases": releases}}
        case "github.lookup_prior_issues":
            return {"result": {"prior_issues": issues}}
        case "github.lookup_branches":
            return {"result": {"branches": [{"name": "main", "protected": True}]}}
        case _:
            raise HTTPException(status_code=404, detail=f"Unsupported GitHub MCP tool: {tool}")


async def _github_app_tool(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    token = await _github_installation_token()
    repository_url = str(
        arguments.get("repository_url") or "https://github.com/AIRP-client/checkout-api"
    )
    owner, name = _repository_owner_name(repository_url)
    repo_path = f"{owner}/{name}"
    limit = _limit(arguments, default=20, maximum=100)

    match tool:
        case "github.list_org_repositories":
            org = str(arguments.get("org") or _github_default_org())
            data = await _github_installation_request(
                "GET",
                f"/orgs/{org}/repos",
                token,
                params={"type": "all", "sort": "updated", "per_page": limit},
            )
            return {"result": {"repositories": [_repo_payload(item) for item in data]}}
        case "github.get_repository":
            data = await _github_installation_request("GET", f"/repos/{repo_path}", token)
            return {"result": {"repository": _repo_payload(data)}}
        case "github.lookup_commits":
            params = {"per_page": limit}
            if arguments.get("since"):
                params["since"] = str(arguments["since"])
            if arguments.get("until"):
                params["until"] = str(arguments["until"])
            data = await _github_installation_request(
                "GET", f"/repos/{repo_path}/commits", token, params=params
            )
            return {"result": {"commits": [_commit_payload(item) for item in data]}}
        case "github.lookup_commit":
            sha = str(arguments.get("sha") or "")
            if not sha:
                commits = await _github_installation_request(
                    "GET", f"/repos/{repo_path}/commits", token, params={"per_page": 1}
                )
                if not commits:
                    return {"result": {"commit": None}}
                sha = commits[0]["sha"]
            data = await _github_installation_request(
                "GET", f"/repos/{repo_path}/commits/{sha}", token
            )
            return {"result": {"commit": _commit_payload(data, include_files=True)}}
        case "github.lookup_merged_prs":
            query = f"repo:{repo_path} is:pr is:merged"
            if arguments.get("since"):
                query = f"{query} merged:>={arguments['since']}"
            data = await _github_installation_request(
                "GET",
                "/search/issues",
                token,
                params={"q": query, "sort": "updated", "order": "desc", "per_page": limit},
            )
            return {
                "result": {
                    "merged_prs": [_pull_request_payload(item) for item in data["items"]]
                }
            }
        case "github.lookup_changed_files":
            files = await _github_changed_files(repo_path, token, arguments, limit)
            return {"result": {"changed_files": files}}
        case "github.lookup_releases":
            data = await _github_installation_request(
                "GET", f"/repos/{repo_path}/releases", token, params={"per_page": limit}
            )
            return {"result": {"releases": [_release_payload(item) for item in data]}}
        case "github.lookup_prior_issues":
            user_query = str(arguments.get("query") or "").strip()
            query = f"repo:{repo_path} is:issue"
            if user_query:
                query = f"{query} {user_query}"
            data = await _github_installation_request(
                "GET",
                "/search/issues",
                token,
                params={"q": query, "sort": "updated", "order": "desc", "per_page": limit},
            )
            return {"result": {"prior_issues": [_issue_payload(item) for item in data["items"]]}}
        case "github.lookup_branches":
            data = await _github_installation_request(
                "GET", f"/repos/{repo_path}/branches", token, params={"per_page": limit}
            )
            return {"result": {"branches": [_branch_payload(item) for item in data]}}
        case _:
            raise HTTPException(status_code=404, detail=f"Unsupported GitHub MCP tool: {tool}")


def _github_app_configured() -> bool:
    return bool(os.getenv("AIRP_GITHUB_APP_ID") and _github_private_key())


def _github_default_org() -> str:
    return os.getenv("AIRP_GITHUB_APP_ORG") or os.getenv("AIRP_CLIENT_GITHUB_ORG") or "AIRP-client"


def _github_private_key() -> str | None:
    private_key_b64 = os.getenv("AIRP_GITHUB_APP_PRIVATE_KEY_B64")
    if private_key_b64:
        try:
            return base64.b64decode(private_key_b64, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return None

    private_key_file = os.getenv("AIRP_GITHUB_APP_PRIVATE_KEY_FILE")
    if private_key_file:
        try:
            with open(private_key_file, encoding="utf-8") as file:
                return file.read()
        except OSError:
            return None

    private_key = os.getenv("AIRP_GITHUB_APP_PRIVATE_KEY")
    if private_key:
        return private_key.replace("\\n", "\n")
    return None


def _github_app_jwt() -> str:
    private_key = _github_private_key()
    app_id = os.getenv("AIRP_GITHUB_APP_ID")
    if not app_id or not private_key:
        raise HTTPException(status_code=503, detail="GitHub App credentials are not configured")
    now = int(time.time())
    return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": app_id}, private_key, "RS256")


async def _github_installation_token() -> str:
    cached_token = _GITHUB_TOKEN_CACHE.get("token")
    expires_at = float(_GITHUB_TOKEN_CACHE.get("expires_at", 0))
    if cached_token and expires_at > time.time() + 60:
        return str(cached_token)

    app_jwt = _github_app_jwt()
    installation_id = await _github_installation_id(app_jwt)
    data = await _github_request(
        "POST",
        f"/app/installations/{installation_id}/access_tokens",
        token=app_jwt,
    )
    token = str(data["token"])
    _GITHUB_TOKEN_CACHE["token"] = token
    _GITHUB_TOKEN_CACHE["expires_at"] = time.time() + 3300
    return token


async def _github_installation_id(app_jwt: str) -> str:
    configured = os.getenv("AIRP_GITHUB_APP_INSTALLATION_ID")
    if configured:
        return configured
    data = await _github_request(
        "GET",
        f"/orgs/{_github_default_org()}/installation",
        token=app_jwt,
    )
    return str(data["id"])


async def _github_installation_request(
    method: str,
    path: str,
    token: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    return await _github_request(method, path, token=token, params=params)


async def _github_request(
    method: str,
    path: str,
    *,
    token: str,
    params: dict[str, Any] | None = None,
) -> Any:
    url = f"{os.getenv('AIRP_GITHUB_API_BASE_URL', 'https://api.github.com').rstrip('/')}{path}"
    headers = {
        "accept": "application/vnd.github+json",
        "authorization": f"Bearer {token}",
        "x-github-api-version": "2022-11-28",
    }
    timeout = float(os.getenv("AIRP_GITHUB_APP_API_TIMEOUT_SECONDS", "20"))
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(method, url, headers=headers, params=params)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=_github_error(response))
    if not response.content:
        return {}
    return response.json()


async def _github_changed_files(
    repo_path: str,
    token: str,
    arguments: dict[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    ref = arguments.get("ref")
    if ref:
        data = await _github_installation_request(
            "GET", f"/repos/{repo_path}/commits/{ref}", token
        )
        return [_changed_file_payload(item) for item in data.get("files", [])[:limit]]

    commits = await _github_installation_request(
        "GET", f"/repos/{repo_path}/commits", token, params={"per_page": min(limit, 10)}
    )
    files: list[dict[str, Any]] = []
    for commit in commits:
        detail = await _github_installation_request(
            "GET", f"/repos/{repo_path}/commits/{commit['sha']}", token
        )
        files.extend(_changed_file_payload(item) for item in detail.get("files", []))
        if len(files) >= limit:
            break
    return files[:limit]


def _repo_payload(item: dict[str, Any]) -> dict[str, Any]:
    owner = item.get("owner") or {}
    owner_login = owner.get("login") if isinstance(owner, dict) else str(owner)
    name = str(item.get("name") or "")
    return {
        "name": name,
        "owner": owner_login,
        "full_name": item.get("full_name") or f"{owner_login}/{name}",
        "html_url": item.get("html_url"),
        "default_branch": item.get("default_branch"),
    }


def _commit_payload(item: dict[str, Any], *, include_files: bool = False) -> dict[str, Any]:
    commit = item.get("commit") or {}
    author = item.get("author") or {}
    commit_author = commit.get("author") or {}
    payload = {
        "sha": item.get("sha"),
        "message": commit.get("message"),
        "author": author.get("login") or commit_author.get("name"),
        "authored_at": commit_author.get("date"),
        "url": item.get("html_url"),
        "changed_files": [],
        "raw": {"html_url": item.get("html_url")},
    }
    if include_files:
        payload["changed_files"] = [
            _changed_file_payload(file_item) for file_item in item.get("files", [])
        ]
    return payload


def _changed_file_payload(item: dict[str, Any]) -> dict[str, Any]:
    patch = item.get("patch")
    return {
        "path": item.get("filename"),
        "status": item.get("status"),
        "additions": item.get("additions"),
        "deletions": item.get("deletions"),
        "patch_excerpt": patch[:1000] if isinstance(patch, str) else None,
        "raw": {"html_url": item.get("blob_url") or item.get("raw_url")},
    }


def _pull_request_payload(item: dict[str, Any]) -> dict[str, Any]:
    user = item.get("user") or {}
    return {
        "number": item.get("number"),
        "title": item.get("title"),
        "url": item.get("html_url"),
        "author": user.get("login") if isinstance(user, dict) else None,
        "merged_at": item.get("closed_at"),
        "merge_commit_sha": None,
        "changed_files": [],
        "raw": {"html_url": item.get("html_url")},
    }


def _release_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "tag_name": item.get("tag_name"),
        "name": item.get("name"),
        "target_commitish": item.get("target_commitish"),
        "published_at": item.get("published_at"),
        "url": item.get("html_url"),
        "raw": {"html_url": item.get("html_url")},
    }


def _issue_payload(item: dict[str, Any]) -> dict[str, Any]:
    labels = item.get("labels") or []
    return {
        "number": item.get("number"),
        "title": item.get("title"),
        "url": item.get("html_url"),
        "state": item.get("state"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "labels": [label.get("name") for label in labels if isinstance(label, dict)],
        "raw": {"html_url": item.get("html_url")},
    }


def _branch_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {"name": item.get("name"), "protected": item.get("protected", False)}


def _github_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"GitHub API request failed with HTTP {response.status_code}"
    message = payload.get("message") if isinstance(payload, dict) else None
    return str(message or f"GitHub API request failed with HTTP {response.status_code}")


def _limit(arguments: dict[str, Any], *, default: int, maximum: int) -> int:
    try:
        value = int(arguments.get("limit") or default)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum))


def _repository_owner_name(repository_url: str) -> tuple[str, str]:
    path = repository_url.rstrip("/").removesuffix(".git").split("github.com/")[-1]
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        return "AIRP-client", parts[0] if parts else "checkout-api"
    return parts[-2], parts[-1]

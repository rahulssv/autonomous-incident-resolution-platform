from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
import time
from pathlib import Path
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
    if SERVER_TYPE == "kubernetes":
        payload["mode"] = _kubernetes_health_mode()
        payload["context"] = _kubernetes_context() or "<current>"
        payload["default_namespace"] = _kubernetes_default_namespace()
    if SERVER_TYPE == "github":
        payload["mode"] = "github_app" if _github_app_configured() else "fixture"
        payload["org"] = _github_default_org()
    return payload


@app.post("/tools/call")
async def call_tool(payload: ToolCallRequest) -> dict[str, Any]:
    if SERVER_TYPE == "kubernetes":
        return await _kubernetes_tool(payload.tool, payload.arguments)
    if SERVER_TYPE == "github":
        return await _github_tool(payload.tool, payload.arguments)
    raise HTTPException(status_code=500, detail=f"Unsupported local MCP server: {SERVER_TYPE}")


async def _kubernetes_tool(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if _kubernetes_cluster_configured():
        return await asyncio.to_thread(_kubernetes_cluster_tool, tool, arguments)
    if _kubernetes_cluster_requested():
        raise HTTPException(
            status_code=503,
            detail="Kubernetes MCP cluster mode is enabled but kubeconfig is not readable",
        )
    return _kubernetes_fixture_tool(tool, arguments)


def _kubernetes_fixture_tool(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
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
            raise HTTPException(
                status_code=404,
                detail=f"Unsupported Kubernetes MCP tool: {tool}",
            )


def _kubernetes_cluster_tool(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    core_api, apps_api = _kubernetes_api_clients()
    namespace = str(arguments.get("namespace") or _kubernetes_default_namespace())
    limit = _limit(arguments, default=100, maximum=500)

    try:
        match tool:
            case "kubernetes.list_pods":
                _ensure_kubernetes_namespace_allowed(namespace)
                pods = core_api.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=_optional_string(arguments.get("label_selector")),
                    field_selector=_optional_string(arguments.get("field_selector")),
                    limit=limit,
                ).items
                return {"result": {"pods": [_kubernetes_pod_payload(pod) for pod in pods]}}
            case "kubernetes.get_pod":
                _ensure_kubernetes_namespace_allowed(namespace)
                pod_name = _required_argument(arguments, "pod_name")
                pod = core_api.read_namespaced_pod(name=pod_name, namespace=namespace)
                return {"result": {"pod": _kubernetes_pod_payload(pod)}}
            case "kubernetes.get_pod_logs":
                _ensure_kubernetes_namespace_allowed(namespace)
                pod_name = _required_argument(arguments, "pod_name")
                limit_lines = _limit(arguments, default=200, maximum=2000)
                text = core_api.read_namespaced_pod_log(
                    name=pod_name,
                    namespace=namespace,
                    container=_optional_string(arguments.get("container")),
                    tail_lines=limit_lines,
                    since_seconds=_optional_int(arguments.get("since_seconds")),
                )
                lines = str(text or "").splitlines()
                return {
                    "result": {
                        "namespace": namespace,
                        "pod_name": pod_name,
                        "container": _optional_string(arguments.get("container")),
                        "lines": lines[-limit_lines:],
                        "truncated": len(lines) > limit_lines,
                        "raw": {"source_link": f"kubernetes://{namespace}/pods/{pod_name}/logs"},
                    }
                }
            case "kubernetes.list_events":
                _ensure_kubernetes_namespace_allowed(namespace)
                events = core_api.list_namespaced_event(namespace=namespace, limit=limit).items
                events = sorted(events, key=_kubernetes_event_sort_key, reverse=True)
                return {
                    "result": {
                        "events": [_kubernetes_event_payload(event) for event in events[:limit]]
                    }
                }
            case "kubernetes.get_deployment":
                _ensure_kubernetes_namespace_allowed(namespace)
                deployment_name = _required_argument(arguments, "deployment")
                deployment = apps_api.read_namespaced_deployment(
                    name=deployment_name,
                    namespace=namespace,
                )
                return {"result": {"deployment": _kubernetes_deployment_payload(deployment)}}
            case "kubernetes.get_rollout_status":
                _ensure_kubernetes_namespace_allowed(namespace)
                deployment_name = _required_argument(arguments, "deployment")
                deployment = apps_api.read_namespaced_deployment(
                    name=deployment_name,
                    namespace=namespace,
                )
                return {
                    "result": {
                        "rollout_status": _kubernetes_rollout_payload(deployment)
                    }
                }
            case "kubernetes.list_replicasets":
                _ensure_kubernetes_namespace_allowed(namespace)
                deployment_name = _optional_string(arguments.get("deployment"))
                label_selector = None
                if deployment_name:
                    deployment = apps_api.read_namespaced_deployment(
                        name=deployment_name,
                        namespace=namespace,
                    )
                    label_selector = _kubernetes_selector(deployment)
                replica_sets = apps_api.list_namespaced_replica_set(
                    namespace=namespace,
                    label_selector=label_selector,
                    limit=limit,
                ).items
                if deployment_name:
                    replica_sets = [
                        item
                        for item in replica_sets
                        if _kubernetes_replica_set_deployment(item) == deployment_name
                    ]
                return {
                    "result": {
                        "replica_sets": [
                            _kubernetes_replica_set_payload(item) for item in replica_sets[:limit]
                        ]
                    }
                }
            case _:
                raise HTTPException(
                    status_code=404,
                    detail=f"Unsupported Kubernetes MCP tool: {tool}",
                )
    except HTTPException:
        raise
    except Exception as exc:
        raise _kubernetes_http_exception(exc) from exc


def _kubernetes_api_clients() -> tuple[Any, Any]:
    try:
        from kubernetes import client, config
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="The kubernetes Python package is not installed in this image",
        ) from exc

    kubeconfig = _kubernetes_kubeconfig_path()
    if kubeconfig is None or not kubeconfig.is_file():
        raise HTTPException(status_code=503, detail="Kubernetes kubeconfig is not readable")

    try:
        config.load_kube_config(
            config_file=str(kubeconfig),
            context=_kubernetes_context(),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Kubernetes kubeconfig could not be loaded: {type(exc).__name__}",
        ) from exc
    return client.CoreV1Api(), client.AppsV1Api()


def _kubernetes_health_mode() -> str:
    if _kubernetes_cluster_configured():
        return "cluster"
    if _kubernetes_cluster_requested():
        return "cluster_unavailable"
    return "fixture"


def _kubernetes_cluster_requested() -> bool:
    return os.getenv("AIRP_KUBERNETES_MCP_MODE", "fixture").lower() in {"cluster", "live"}


def _kubernetes_cluster_configured() -> bool:
    if not _kubernetes_cluster_requested():
        return False
    kubeconfig = _kubernetes_kubeconfig_path()
    return kubeconfig is not None and kubeconfig.is_file()


def _kubernetes_kubeconfig_path() -> Path | None:
    raw_path = os.getenv("AIRP_KUBERNETES_KUBECONFIG") or os.getenv("KUBECONFIG")
    if not raw_path:
        return None
    return Path(raw_path).expanduser()


def _kubernetes_context() -> str | None:
    return _optional_string(os.getenv("AIRP_KUBERNETES_CONTEXT"))


def _kubernetes_default_namespace() -> str:
    return os.getenv("AIRP_KUBERNETES_DEFAULT_NAMESPACE") or "default"


def _kubernetes_namespace_allowlist() -> list[str]:
    raw_value = os.getenv("AIRP_KUBERNETES_MCP_NAMESPACE_ALLOWLIST", "")
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        parsed = [item.strip() for item in raw_value.split(",")]
    if isinstance(parsed, str):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _ensure_kubernetes_namespace_allowed(namespace: str) -> None:
    allowed_namespaces = _kubernetes_namespace_allowlist()
    if allowed_namespaces and namespace not in allowed_namespaces:
        raise HTTPException(
            status_code=403,
            detail=f"Namespace {namespace!r} is not in AIRP_KUBERNETES_MCP_NAMESPACE_ALLOWLIST",
        )


def _kubernetes_pod_payload(pod: Any) -> dict[str, Any]:
    metadata = pod.metadata
    spec = pod.spec
    status = pod.status
    containers = list(getattr(spec, "containers", None) or [])
    container_statuses = list(getattr(status, "container_statuses", None) or [])
    restart_count = sum(int(item.restart_count or 0) for item in container_statuses)
    ready = all(bool(item.ready) for item in container_statuses) if container_statuses else None
    return {
        "namespace": metadata.namespace,
        "name": metadata.name,
        "phase": status.phase,
        "ready": ready,
        "restart_count": restart_count if container_statuses else None,
        "node_name": spec.node_name,
        "pod_ip": status.pod_ip,
        "containers": [container.name for container in containers],
        "images": [container.image for container in containers if container.image],
        "labels": dict(metadata.labels or {}),
        "raw": {
            "source_link": f"kubernetes://{metadata.namespace}/pods/{metadata.name}",
            "uid": metadata.uid,
        },
    }


def _kubernetes_event_payload(event: Any) -> dict[str, Any]:
    metadata = event.metadata
    involved_object = event.involved_object
    timestamp = (
        getattr(event, "event_time", None)
        or getattr(event, "last_timestamp", None)
        or getattr(event, "first_timestamp", None)
        or getattr(metadata, "creation_timestamp", None)
    )
    involved_name = getattr(involved_object, "name", None)
    return {
        "namespace": metadata.namespace,
        "reason": event.reason or "",
        "message": event.message or "",
        "type": event.type,
        "involved_object": involved_name,
        "timestamp": _isoformat(timestamp),
        "raw": {
            "source_link": f"kubernetes://{metadata.namespace}/events/{metadata.name}",
            "involved_kind": getattr(involved_object, "kind", None),
        },
    }


def _kubernetes_deployment_payload(deployment: Any) -> dict[str, Any]:
    metadata = deployment.metadata
    spec = deployment.spec
    status = deployment.status
    pod_spec = deployment.spec.template.spec
    containers = list(getattr(pod_spec, "containers", None) or [])
    return {
        "namespace": metadata.namespace,
        "name": metadata.name,
        "desired_replicas": spec.replicas,
        "ready_replicas": status.ready_replicas,
        "updated_replicas": status.updated_replicas,
        "available_replicas": status.available_replicas,
        "images": [container.image for container in containers if container.image],
        "labels": dict(metadata.labels or {}),
        "raw": {
            "source_link": f"kubernetes://{metadata.namespace}/deployments/{metadata.name}",
            "generation": metadata.generation,
            "observed_generation": status.observed_generation,
        },
    }


def _kubernetes_rollout_payload(deployment: Any) -> dict[str, Any]:
    metadata = deployment.metadata
    spec = deployment.spec
    status = deployment.status
    desired = int(spec.replicas or 0)
    updated = int(status.updated_replicas or 0)
    ready = int(status.ready_replicas or 0)
    available = int(status.available_replicas or 0)
    observed_generation = int(status.observed_generation or 0)
    generation = int(metadata.generation or 0)
    if observed_generation < generation:
        rollout_status = "progressing"
    elif updated >= desired and ready >= desired and available >= desired:
        rollout_status = "healthy"
    else:
        rollout_status = "degraded"
    return {
        "namespace": metadata.namespace,
        "deployment": metadata.name,
        "status": rollout_status,
        "message": (
            f"{ready}/{desired} ready, {updated}/{desired} updated, "
            f"{available}/{desired} available"
        ),
        "raw": {
            "source_link": f"kubernetes://{metadata.namespace}/rollouts/{metadata.name}",
            "generation": generation,
            "observed_generation": observed_generation,
        },
    }


def _kubernetes_replica_set_payload(replica_set: Any) -> dict[str, Any]:
    metadata = replica_set.metadata
    spec = replica_set.spec
    status = replica_set.status
    pod_spec = replica_set.spec.template.spec
    containers = list(getattr(pod_spec, "containers", None) or [])
    return {
        "namespace": metadata.namespace,
        "name": metadata.name,
        "deployment": _kubernetes_replica_set_deployment(replica_set),
        "desired_replicas": spec.replicas,
        "ready_replicas": status.ready_replicas,
        "images": [container.image for container in containers if container.image],
        "raw": {
            "source_link": f"kubernetes://{metadata.namespace}/replicasets/{metadata.name}",
            "uid": metadata.uid,
        },
    }


def _kubernetes_replica_set_deployment(replica_set: Any) -> str | None:
    for owner in replica_set.metadata.owner_references or []:
        if owner.kind == "Deployment":
            return owner.name
    return None


def _kubernetes_selector(deployment: Any) -> str | None:
    match_labels = deployment.spec.selector.match_labels or {}
    if not match_labels:
        return None
    return ",".join(f"{key}={value}" for key, value in sorted(match_labels.items()))


def _kubernetes_event_sort_key(event: Any) -> str:
    timestamp = (
        getattr(event, "event_time", None)
        or getattr(event, "last_timestamp", None)
        or getattr(event, "first_timestamp", None)
        or getattr(event.metadata, "creation_timestamp", None)
    )
    return _isoformat(timestamp) or ""


def _kubernetes_http_exception(exc: Exception) -> HTTPException:
    status = getattr(exc, "status", None)
    reason = getattr(exc, "reason", None)
    if status is not None:
        status_code = 404 if status == 404 else 502
        return HTTPException(
            status_code=status_code,
            detail=f"Kubernetes API request failed with HTTP {status}: {reason or 'error'}",
        )
    return HTTPException(
        status_code=502,
        detail=f"Kubernetes API request failed: {type(exc).__name__}",
    )


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
            "author": "airp-local",
            "authored_at": "2026-05-16T00:00:00Z",
            "url": f"{repository_url}/commit/localmcp1234567890",
            "changed_files": changed_files,
            "raw": {
                "html_url": f"{repository_url}/commit/localmcp1234567890",
                "author_login": "airp-local",
            },
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
        case "github.lookup_file_commits":
            path = str(arguments.get("path") or "")
            matches = [
                commit
                for commit in commits
                if any(item["path"] == path for item in commit["changed_files"])
            ]
            return {"result": {"commits": matches or commits}}
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
        case "github.create_issue":
            title = str(arguments.get("title") or "AIRP incident")
            body = str(arguments.get("body") or "")
            issue = {
                "number": 9999,
                "title": title,
                "body": body,
                "url": f"{repository_url}/issues/9999",
                "state": "open",
                "created_at": "2026-05-16T00:00:00Z",
                "updated_at": "2026-05-16T00:00:00Z",
                "labels": list(arguments.get("labels") or []),
                "raw": {"html_url": f"{repository_url}/issues/9999", "fixture": True},
            }
            return {"result": {"issue": issue}}
        case "github.create_pull_request":
            title = str(arguments.get("title") or "AIRP remediation")
            branch = str(arguments.get("branch") or "airp/remediation/local")
            pull_request = {
                "number": 10000,
                "title": title,
                "url": f"{repository_url}/pull/10000",
                "author": "airp-local",
                "head": branch,
                "base": str(arguments.get("base") or "main"),
                "assignees": list(arguments.get("assignees") or []),
                "changed_files": list(arguments.get("files") or []),
                "existing": False,
                "raw": {"html_url": f"{repository_url}/pull/10000", "fixture": True},
            }
            return {"result": {"pull_request": pull_request}}
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
        case "github.lookup_file_commits":
            path = _required_argument(arguments, "path")
            data = await _github_installation_request(
                "GET",
                f"/repos/{repo_path}/commits",
                token,
                params={"path": path, "per_page": limit},
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
        case "github.create_issue":
            title = str(arguments.get("title") or "").strip()
            body = str(arguments.get("body") or "").strip()
            labels = [str(label) for label in arguments.get("labels") or [] if label]
            if not title or not body:
                raise HTTPException(
                    status_code=400,
                    detail="github.create_issue requires title and body",
                )
            issue_payload = {"title": title, "body": body, "labels": labels}
            try:
                data = await _github_installation_request(
                    "POST",
                    f"/repos/{repo_path}/issues",
                    token,
                    json_body=issue_payload,
                )
            except HTTPException as exc:
                if exc.status_code != 422 or not labels:
                    raise
                data = await _github_installation_request(
                    "POST",
                    f"/repos/{repo_path}/issues",
                    token,
                    json_body={"title": title, "body": body},
                )
            return {"result": {"issue": _issue_payload(data)}}
        case "github.create_pull_request":
            pull_request = await _github_create_pull_request(repo_path, token, arguments)
            return {"result": {"pull_request": pull_request}}
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
    json_body: dict[str, Any] | None = None,
) -> Any:
    return await _github_request(method, path, token=token, params=params, json_body=json_body)


async def _github_request(
    method: str,
    path: str,
    *,
    token: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    url = f"{os.getenv('AIRP_GITHUB_API_BASE_URL', 'https://api.github.com').rstrip('/')}{path}"
    headers = {
        "accept": "application/vnd.github+json",
        "authorization": f"Bearer {token}",
        "x-github-api-version": "2022-11-28",
    }
    timeout = float(os.getenv("AIRP_GITHUB_APP_API_TIMEOUT_SECONDS", "20"))
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(method, url, headers=headers, params=params, json=json_body)
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


async def _github_create_pull_request(
    repo_path: str,
    token: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    title = str(arguments.get("title") or "").strip()
    body = str(arguments.get("body") or "").strip()
    branch = str(arguments.get("branch") or "").strip()
    raw_files = arguments.get("files") or []
    if not title or not body or not branch:
        raise HTTPException(
            status_code=400,
            detail="github.create_pull_request requires title, body, and branch",
        )
    if not isinstance(raw_files, list) or not raw_files:
        raise HTTPException(
            status_code=400,
            detail="github.create_pull_request requires at least one file change",
        )

    repo = await _github_installation_request("GET", f"/repos/{repo_path}", token)
    base_branch = str(arguments.get("base") or repo.get("default_branch") or "main")
    existing = await _github_existing_pull_request(repo_path, token, branch)
    if existing is not None:
        payload = _pull_request_payload(existing)
        payload["existing"] = True
        payload["assignees"] = _assignee_logins(existing.get("assignees") or [])
        return payload

    await _github_create_branch(repo_path, token, branch, from_branch=base_branch)
    changed_files = []
    for file_change in raw_files:
        if not isinstance(file_change, dict):
            raise HTTPException(status_code=400, detail="file changes must be objects")
        path = _required_argument(file_change, "path").strip("/")
        content = str(file_change.get("content") or "")
        message = str(file_change.get("message") or f"Update {path}").strip()
        await _github_upsert_file(
            repo_path,
            token,
            path=path,
            content=content,
            message=message,
            branch=branch,
        )
        changed_files.append({"path": path, "status": "modified"})

    existing_created_pr = False
    try:
        data = await _github_installation_request(
            "POST",
            f"/repos/{repo_path}/pulls",
            token,
            json_body={
                "title": title,
                "body": body,
                "head": branch,
                "base": base_branch,
                "maintainer_can_modify": True,
            },
        )
    except HTTPException as exc:
        if exc.status_code != 422:
            raise
        existing_pr = await _github_existing_pull_request(repo_path, token, branch)
        if existing_pr is None:
            raise
        data = existing_pr
        existing_created_pr = True

    assignees = [
        str(assignee)
        for assignee in arguments.get("assignees") or []
        if str(assignee).strip()
    ]
    assignment_error = None
    if assignees:
        try:
            assigned = await _github_installation_request(
                "POST",
                f"/repos/{repo_path}/issues/{data['number']}/assignees",
                token,
                json_body={"assignees": assignees},
            )
            assignees = _assignee_logins(assigned.get("assignees") or [])
        except HTTPException as exc:
            assignment_error = str(exc.detail)

    payload = _pull_request_payload(data)
    payload["changed_files"] = changed_files
    payload["assignees"] = assignees
    payload["assignment_error"] = assignment_error
    payload["existing"] = existing_created_pr
    return payload


async def _github_existing_pull_request(
    repo_path: str,
    token: str,
    branch: str,
) -> dict[str, Any] | None:
    owner = repo_path.split("/", 1)[0]
    data = await _github_installation_request(
        "GET",
        f"/repos/{repo_path}/pulls",
        token,
        params={"head": f"{owner}:{branch}", "state": "open", "per_page": 1},
    )
    return data[0] if data else None


async def _github_create_branch(
    repo_path: str,
    token: str,
    branch: str,
    *,
    from_branch: str,
) -> dict[str, Any]:
    source = await _github_installation_request(
        "GET",
        f"/repos/{repo_path}/git/ref/heads/{from_branch}",
        token,
    )
    sha = source.get("object", {}).get("sha")
    if not sha:
        raise HTTPException(status_code=502, detail="GitHub branch source SHA was unavailable")
    try:
        return await _github_installation_request(
            "POST",
            f"/repos/{repo_path}/git/refs",
            token,
            json_body={"ref": f"refs/heads/{branch}", "sha": sha},
        )
    except HTTPException as exc:
        if exc.status_code != 422:
            raise
        return await _github_installation_request(
            "GET",
            f"/repos/{repo_path}/git/ref/heads/{branch}",
            token,
        )


async def _github_get_file(
    repo_path: str,
    token: str,
    *,
    path: str,
    ref: str,
) -> dict[str, Any] | None:
    try:
        data = await _github_installation_request(
            "GET",
            f"/repos/{repo_path}/contents/{path}",
            token,
            params={"ref": ref},
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            return None
        raise
    return data if isinstance(data, dict) else None


async def _github_upsert_file(
    repo_path: str,
    token: str,
    *,
    path: str,
    content: str,
    message: str,
    branch: str,
) -> dict[str, Any]:
    existing = await _github_get_file(repo_path, token, path=path, ref=branch)
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if existing and existing.get("sha"):
        payload["sha"] = existing["sha"]
    return await _github_installation_request(
        "PUT",
        f"/repos/{repo_path}/contents/{path}",
        token,
        json_body=payload,
    )


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
    committer = item.get("committer") or {}
    commit_author = commit.get("author") or {}
    author_login = author.get("login") if isinstance(author, dict) else None
    committer_login = committer.get("login") if isinstance(committer, dict) else None
    payload = {
        "sha": item.get("sha"),
        "message": commit.get("message"),
        "author": author_login or commit_author.get("name"),
        "authored_at": commit_author.get("date"),
        "url": item.get("html_url"),
        "changed_files": [],
        "raw": {
            "html_url": item.get("html_url"),
            "author_login": author_login,
            "committer_login": committer_login,
        },
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
    head = item.get("head") if isinstance(item.get("head"), dict) else {}
    base = item.get("base") if isinstance(item.get("base"), dict) else {}
    return {
        "number": item.get("number"),
        "title": item.get("title"),
        "url": item.get("html_url"),
        "author": user.get("login") if isinstance(user, dict) else None,
        "merged_at": item.get("closed_at"),
        "merge_commit_sha": None,
        "head": head.get("ref"),
        "base": base.get("ref"),
        "assignees": _assignee_logins(item.get("assignees") or []),
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
        "body": item.get("body"),
        "url": item.get("html_url"),
        "state": item.get("state"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "labels": [label.get("name") for label in labels if isinstance(label, dict)],
        "raw": {"html_url": item.get("html_url")},
    }


def _branch_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {"name": item.get("name"), "protected": item.get("protected", False)}


def _assignee_logins(items: list[Any]) -> list[str]:
    logins = []
    for item in items:
        if isinstance(item, dict) and item.get("login"):
            logins.append(str(item["login"]))
        elif isinstance(item, str) and item:
            logins.append(item)
    return logins


def _github_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"GitHub API request failed with HTTP {response.status_code}"
    message = payload.get("message") if isinstance(payload, dict) else None
    return str(message or f"GitHub API request failed with HTTP {response.status_code}")


def _required_argument(arguments: dict[str, Any], name: str) -> str:
    value = _optional_string(arguments.get(name))
    if not value:
        raise HTTPException(status_code=400, detail=f"{name} is required")
    return value


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


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

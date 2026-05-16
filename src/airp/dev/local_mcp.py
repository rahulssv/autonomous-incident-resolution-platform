from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel):
    tool: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


SERVER_TYPE = os.getenv("AIRP_LOCAL_MCP_SERVER", "kubernetes")
app = FastAPI(title=f"AIRP Local {SERVER_TYPE.title()} MCP")


@app.get("/")
async def health() -> dict[str, str]:
    return {
        "service": f"airp-local-{SERVER_TYPE}-mcp",
        "status": "ok",
        "transport": "mcp-http-bridge",
    }


@app.post("/tools/call")
async def call_tool(payload: ToolCallRequest) -> dict[str, Any]:
    if SERVER_TYPE == "kubernetes":
        return _kubernetes_tool(payload.tool, payload.arguments)
    if SERVER_TYPE == "github":
        return _github_tool(payload.tool, payload.arguments)
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


def _github_tool(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
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


def _repository_owner_name(repository_url: str) -> tuple[str, str]:
    path = repository_url.rstrip("/").removesuffix(".git").split("github.com/")[-1]
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        return "AIRP-client", parts[0] if parts else "checkout-api"
    return parts[-2], parts[-1]

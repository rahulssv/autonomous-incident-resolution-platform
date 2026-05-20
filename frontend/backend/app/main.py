from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .auth import router as auth_router, token_from_request
from .config import settings
from .graph_service import GRAPH_STAGES, stream_demo_resolution
from .graph_service import (
    get_resolution_incident,
    list_resolution_incidents,
    stream_incident_resolution,
)
from .github_client import GitHubAPIError, GitHubClient
from .github_service import (
    build_user_activity,
    build_dashboard,
    get_issue_timeline,
    get_org,
    get_pull_request_reviews,
    get_viewer,
    list_org_repos,
    search_issues,
    search_pull_requests,
)


app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])


def _bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.lower() == "bearer" and token:
        return token.strip()
    return None


async def github_client(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> GitHubClient:
    token = _bearer_token(authorization) or token_from_request(request) or settings.github_token
    return GitHubClient(settings, token=token)


@app.exception_handler(GitHubAPIError)
async def github_api_exception_handler(
    _request: Request, exc: GitHubAPIError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "details": exc.details,
            "githubHeaders": {
                key: value
                for key, value in exc.headers.items()
                if key.lower().startswith("x-github") or key.lower().startswith("x-ratelimit")
            },
        },
    )


@app.get("/api/health")
async def health() -> dict[str, str | bool]:
    return {
        "ok": True,
        "service": settings.app_name,
        "githubTokenConfigured": bool(settings.github_token),
        "githubOAuthConfigured": bool(
            settings.github_oauth_client_id and settings.github_oauth_client_secret
        ),
        "githubApiVersion": settings.github_api_version,
    }


@app.get("/api/github/me")
async def me(client: Annotated[GitHubClient, Depends(github_client)]) -> dict:
    return await get_viewer(client)


@app.get("/api/github/orgs")
async def orgs(client: Annotated[GitHubClient, Depends(github_client)]) -> dict:
    viewer = await get_viewer(client)
    return {"items": viewer["organizations"], "viewer": viewer}


@app.get("/api/github/orgs/{org}")
async def organization(
    org: str, client: Annotated[GitHubClient, Depends(github_client)]
) -> dict:
    return await get_org(client, org)


@app.get("/api/github/orgs/{org}/repos")
async def repositories(
    org: str,
    client: Annotated[GitHubClient, Depends(github_client)],
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
    page: Annotated[int, Query(ge=1)] = 1,
    repo_type: Literal["all", "public", "private", "forks", "sources", "member"] = "all",
) -> dict:
    return {
        "items": await list_org_repos(
            client, org, per_page=per_page, page=page, repo_type=repo_type
        )
    }


@app.get("/api/github/orgs/{org}/issues")
async def issues(
    org: str,
    client: Annotated[GitHubClient, Depends(github_client)],
    state: Literal["open", "closed", "all"] = "open",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    labels: str | None = None,
    repo: str | None = None,
    assignee: str | None = None,
    author: str | None = None,
    q: str | None = None,
) -> dict:
    return await search_issues(
        client,
        org,
        state=state,
        limit=limit,
        labels=labels,
        repo=repo,
        assignee=assignee,
        author=author,
        query=q,
    )


@app.get("/api/github/orgs/{org}/pull-requests")
async def pull_requests(
    org: str,
    client: Annotated[GitHubClient, Depends(github_client)],
    state: Literal["open", "closed", "all"] = "open",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    labels: str | None = None,
    repo: str | None = None,
    assignee: str | None = None,
    author: str | None = None,
    q: str | None = None,
) -> dict:
    return await search_pull_requests(
        client,
        org,
        state=state,
        limit=limit,
        labels=labels,
        repo=repo,
        assignee=assignee,
        author=author,
        query=q,
    )


@app.get("/api/github/orgs/{org}/dashboard")
async def dashboard(
    org: str,
    client: Annotated[GitHubClient, Depends(github_client)],
    state: Literal["open", "closed", "all"] = "open",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    labels: str | None = None,
    repo: str | None = None,
    assignee: str | None = None,
    bot: str | None = None,
    q: str | None = None,
) -> dict:
    return await build_dashboard(
        client,
        org,
        state=state,
        limit=limit,
        labels=labels,
        repo=repo,
        assignee=assignee,
        query=q,
        bot_login=bot,
    )


@app.get("/api/github/orgs/{org}/user-activity")
async def user_activity(
    org: str,
    client: Annotated[GitHubClient, Depends(github_client)],
    user: Annotated[str, Query(min_length=1)],
    days: Annotated[int, Query(ge=1, le=31)] = 21,
) -> dict:
    return await build_user_activity(client, org, user=user, days=days)


@app.get("/api/github/repos/{owner}/{repo}/issues/{number}/timeline")
async def issue_timeline(
    owner: str,
    repo: str,
    number: int,
    client: Annotated[GitHubClient, Depends(github_client)],
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict:
    return {"items": await get_issue_timeline(client, owner, repo, number, per_page)}


@app.get("/api/github/repos/{owner}/{repo}/pulls/{number}/reviews")
async def pull_request_reviews(
    owner: str,
    repo: str,
    number: int,
    client: Annotated[GitHubClient, Depends(github_client)],
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict:
    return {"items": await get_pull_request_reviews(client, owner, repo, number, per_page)}


@app.get("/api/github/rate-limit")
async def rate_limit(client: Annotated[GitHubClient, Depends(github_client)]) -> dict:
    return await client.rest("GET", "/rate_limit")


@app.get("/api/graph/stages")
async def graph_stages() -> dict:
    return {
        "source": "langgraph-adapter",
        "items": GRAPH_STAGES,
    }


@app.get("/api/graph/demo-resolution")
async def graph_demo_resolution(
    scenario: Literal["crashloop", "oom", "latency"] = "crashloop",
    severity: Literal["critical", "warning", "info"] = "critical",
    title: str | None = None,
) -> StreamingResponse:
    return StreamingResponse(
        stream_demo_resolution(scenario=scenario, severity=severity, title=title),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/graph/incidents")
async def graph_incidents() -> dict:
    return await list_resolution_incidents()


@app.get("/api/graph/incidents/{incident_id}")
async def graph_incident_detail(incident_id: str) -> JSONResponse:
    detail = await get_resolution_incident(incident_id)
    if not detail:
        return JSONResponse({"detail": "Graph incident not found"}, status_code=404)
    return JSONResponse(detail)


@app.get("/api/graph/incidents/{incident_id}/stream")
async def graph_incident_stream(incident_id: str) -> StreamingResponse:
    return StreamingResponse(
        stream_incident_resolution(incident_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _frontend_dist_dir() -> Path | None:
    env_dir = os.getenv("FRONTEND_DIST_DIR")
    candidates = []
    if env_dir:
        candidates.append(Path(env_dir))
    project_root = Path(__file__).resolve().parents[2]
    candidates.extend(
        [
            project_root / "frontend" / "dist",
            project_root / "dist",
        ]
    )
    for candidate in candidates:
        index_file = candidate / "index.html"
        if index_file.is_file():
            return candidate
    return None


frontend_dist_dir = _frontend_dist_dir()
if frontend_dist_dir:
    assets_dir = frontend_dist_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/", include_in_schema=False, response_model=None)
    async def frontend_index() -> FileResponse:
        return FileResponse(frontend_dist_dir / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def frontend_spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        requested_file = frontend_dist_dir / full_path
        if requested_file.is_file():
            return FileResponse(requested_file)
        return FileResponse(frontend_dist_dir / "index.html")

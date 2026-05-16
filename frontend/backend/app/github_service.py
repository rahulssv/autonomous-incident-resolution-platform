from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from .config import settings
from .github_client import GitHubClient
from .github_queries import ISSUES_SEARCH_QUERY, PULL_REQUESTS_SEARCH_QUERY, VIEWER_QUERY


IssueState = Literal["open", "closed", "all"]

STAGES = [
    "Issue",
    "Linked PR",
    "Review",
    "Checks",
    "Merge / Closure",
]


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _quote_search_value(value: str) -> str:
    if any(char.isspace() for char in value) or ":" in value:
        return f'"{value.replace(chr(34), "")}"'
    return value


def build_search_query(
    org: str,
    item: Literal["issue", "pr"],
    state: IssueState = "open",
    labels: list[str] | None = None,
    repo: str | None = None,
    assignee: str | None = None,
    author: str | None = None,
    extra_query: str | None = None,
) -> str:
    terms = [f"org:{org}", f"is:{item}", "archived:false"]
    if state != "all":
        terms.append(f"is:{state}")
    if repo:
        repo_name = repo if "/" in repo else f"{org}/{repo}"
        terms.append(f"repo:{repo_name}")
    for label in labels or []:
        terms.append(f"label:{_quote_search_value(label)}")
    if assignee:
        terms.append(f"assignee:{assignee}")
    if author:
        terms.append(f"author:{author}")
    if extra_query:
        terms.append(extra_query)
    return " ".join(terms)


def _bot_author_logins(bot_login: str | None) -> list[str]:
    if not bot_login:
        return []
    login = bot_login.strip()
    if not login:
        return []

    authors = [login]
    if login.startswith("app/"):
        return authors

    app_slug = login.removesuffix("[bot]")
    app_author = f"app/{app_slug}"
    if app_author not in authors:
        authors.append(app_author)
    return authors


def _merge_search_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    items_by_id: dict[str, dict[str, Any]] = {}
    for result in results:
        for item in result.get("items", []):
            items_by_id[item["id"]] = item

    return {
        "query": " OR ".join(result["query"] for result in results),
        "queries": [result["query"] for result in results],
        "totalCount": sum(result.get("totalCount") or 0 for result in results),
        "dedupedCount": len(items_by_id),
        "pageInfo": [result.get("pageInfo") for result in results],
        "rateLimit": results[-1].get("rateLimit") if results else None,
        "items": sorted(
            items_by_id.values(),
            key=lambda item: item.get("updatedAt") or item.get("createdAt") or "",
            reverse=True,
        ),
    }


async def get_viewer(client: GitHubClient, org_limit: int = 50) -> dict[str, Any]:
    data = await client.graphql(VIEWER_QUERY, {"first": org_limit})
    viewer = data["viewer"]
    graph_orgs = [
        {
            "id": org["login"],
            "name": org.get("name") or org["login"],
            "githubOrg": org["login"],
            "url": org["url"],
            "avatarUrl": org["avatarUrl"],
            "repositories": org["repositories"]["totalCount"],
        }
        for org in viewer["organizations"]["nodes"]
    ]
    rest_orgs = await get_viewer_organizations_rest(client)
    installation_orgs = await get_viewer_installation_organizations_rest(client)
    organizations = _merge_organizations(installation_orgs, rest_orgs, graph_orgs)
    return {
        "login": viewer["login"],
        "name": viewer.get("name") or viewer["login"],
        "avatarUrl": viewer["avatarUrl"],
        "url": viewer["url"],
        "organizations": organizations,
    }


async def get_viewer_installation_organizations_rest(
    client: GitHubClient,
) -> list[dict[str, Any]]:
    try:
        payload = await client.rest("GET", "/user/installations", {"per_page": 100})
    except Exception:
        return []

    organizations = []
    for installation in payload.get("installations", []):
        account = installation.get("account") or {}
        if installation.get("target_type") != "Organization" or not account.get("login"):
            continue

        login = account["login"]
        organizations.append(
            {
                "id": login,
                "name": account.get("name") or login,
                "githubOrg": login,
                "url": account.get("html_url") or f"https://github.com/{login}",
                "avatarUrl": account.get("avatar_url"),
                "repositories": 0,
                "source": "github-app-installation",
                "installationId": installation.get("id"),
                "repositorySelection": installation.get("repository_selection"),
                "appSlug": installation.get("app_slug"),
                "permissions": installation.get("permissions") or {},
            }
        )
    return sorted(organizations, key=lambda item: item["githubOrg"].lower())


async def get_viewer_organizations_rest(client: GitHubClient) -> list[dict[str, Any]]:
    orgs_by_login: dict[str, dict[str, Any]] = {}

    try:
        orgs = await client.rest("GET", "/user/orgs", {"per_page": 100})
        for org in orgs:
            login = org["login"]
            orgs_by_login[login] = {
                "id": login,
                "name": org.get("name") or login,
                "githubOrg": login,
                "url": org.get("html_url") or f"https://github.com/{login}",
                "avatarUrl": org.get("avatar_url"),
                "repositories": org.get("public_repos", 0),
                "membershipRole": None,
                "membershipState": None,
            }
    except Exception:
        pass

    try:
        memberships = await client.rest(
            "GET", "/user/memberships/orgs", {"per_page": 100, "state": "active"}
        )
        for membership in memberships:
            org = membership.get("organization") or {}
            login = org.get("login")
            if not login:
                continue
            existing = orgs_by_login.get(login, {})
            orgs_by_login[login] = {
                "id": login,
                "name": org.get("name") or existing.get("name") or login,
                "githubOrg": login,
                "url": org.get("html_url") or existing.get("url") or f"https://github.com/{login}",
                "avatarUrl": org.get("avatar_url") or existing.get("avatarUrl"),
                "repositories": existing.get("repositories", 0),
                "membershipRole": membership.get("role"),
                "membershipState": membership.get("state"),
            }
    except Exception:
        pass

    return sorted(orgs_by_login.values(), key=lambda item: item["githubOrg"].lower())


def _merge_organizations(
    *organization_groups: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in organization_groups:
        for org in group:
            login = org["githubOrg"]
            merged[login] = {**merged.get(login, {}), **org}
    return sorted(merged.values(), key=lambda item: item["githubOrg"].lower())


async def get_org(client: GitHubClient, org: str) -> dict[str, Any]:
    raw = await client.rest("GET", f"/orgs/{org}")
    return {
        "id": raw["login"],
        "name": raw.get("name") or raw["login"],
        "githubOrg": raw["login"],
        "plan": (raw.get("plan") or {}).get("name", "GitHub"),
        "repositories": raw.get("public_repos", 0) + raw.get("total_private_repos", 0),
        "publicRepos": raw.get("public_repos", 0),
        "privateRepos": raw.get("total_private_repos"),
        "url": raw.get("html_url"),
        "avatarUrl": raw.get("avatar_url"),
        "description": raw.get("description"),
    }


async def list_org_repos(
    client: GitHubClient,
    org: str,
    per_page: int = 50,
    page: int = 1,
    repo_type: str = "all",
) -> list[dict[str, Any]]:
    repos = await client.rest(
        "GET",
        f"/orgs/{org}/repos",
        {"per_page": per_page, "page": page, "type": repo_type, "sort": "updated"},
    )
    return [
        {
            "id": repo["id"],
            "name": repo["name"],
            "fullName": repo["full_name"],
            "private": repo["private"],
            "url": repo["html_url"],
            "description": repo.get("description"),
            "defaultBranch": repo.get("default_branch"),
            "language": repo.get("language"),
            "openIssues": repo.get("open_issues_count", 0),
            "updatedAt": repo.get("updated_at"),
            "pushedAt": repo.get("pushed_at"),
        }
        for repo in repos
    ]


async def search_issues(
    client: GitHubClient,
    org: str,
    state: IssueState = "open",
    limit: int = 50,
    labels: str | None = None,
    repo: str | None = None,
    assignee: str | None = None,
    author: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    label_list = _split_csv(labels) or settings.issue_label_filter
    search_query = build_search_query(
        org,
        "issue",
        state,
        label_list,
        repo=repo,
        assignee=assignee,
        author=author,
        extra_query=query,
    )
    data = await client.graphql(
        ISSUES_SEARCH_QUERY, {"query": search_query, "first": limit, "after": None}
    )
    search = data["search"]
    return {
        "query": search_query,
        "totalCount": search["issueCount"],
        "pageInfo": search["pageInfo"],
        "rateLimit": data.get("rateLimit"),
        "items": [_normalize_issue(node) for node in search["nodes"] if node],
    }


async def search_pull_requests(
    client: GitHubClient,
    org: str,
    state: IssueState = "open",
    limit: int = 50,
    labels: str | None = None,
    repo: str | None = None,
    assignee: str | None = None,
    author: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    label_list = _split_csv(labels)
    search_query = build_search_query(
        org,
        "pr",
        state,
        label_list,
        repo=repo,
        assignee=assignee,
        author=author,
        extra_query=query,
    )
    data = await client.graphql(
        PULL_REQUESTS_SEARCH_QUERY, {"query": search_query, "first": limit, "after": None}
    )
    search = data["search"]
    return {
        "query": search_query,
        "totalCount": search["issueCount"],
        "pageInfo": search["pageInfo"],
        "rateLimit": data.get("rateLimit"),
        "items": [_normalize_pull_request(node) for node in search["nodes"] if node],
    }


async def build_user_activity(
    client: GitHubClient,
    org: str,
    user: str,
    days: int = 21,
) -> dict[str, Any]:
    safe_days = max(1, min(days, 31))
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=safe_days - 1)
    dates = [today - timedelta(days=safe_days - index - 1) for index in range(safe_days)]

    start_text = start.isoformat()
    today_text = today.isoformat()
    issue_query = (
        f"org:{org} is:issue archived:false author:{user} created:{start_text}..{today_text}"
    )
    pr_query = f"org:{org} is:pr archived:false author:{user} created:{start_text}..{today_text}"
    commit_query = f"org:{org} author:{user} author-date:{start_text}..{today_text}"

    counts_by_date = {
        day.isoformat(): {
            "date": day.isoformat(),
            "label": day.strftime("%a %m/%d"),
            "commits": 0,
            "issues": 0,
            "pullRequests": 0,
        }
        for day in dates
    }

    search_results = await asyncio.gather(
        _search_items(client, "/search/issues", issue_query, sort="created"),
        _search_items(client, "/search/issues", pr_query, sort="created"),
        _search_items(client, "/search/commits", commit_query, sort="author-date"),
    )

    errors = []
    search_totals = {}
    for kind, query, result in zip(
        ("issues", "pullRequests", "commits"),
        (issue_query, pr_query, commit_query),
        search_results,
    ):
        search_totals[kind] = result["totalCount"]
        if result.get("error"):
            errors.append({"kind": kind, "query": query, "error": result["error"]})
            continue
        if result.get("incomplete"):
            errors.append({"kind": kind, "query": query, "error": "GitHub search results were incomplete."})
        if result.get("truncated"):
            errors.append(
                {
                    "kind": kind,
                    "query": query,
                    "error": f"Grouped first {len(result['items'])} of {result['totalCount']} results.",
                }
            )
        for item in result["items"]:
            date_text = _activity_date(kind, item)
            if date_text in counts_by_date:
                counts_by_date[date_text][kind] += 1

    day_values = list(counts_by_date.values())
    totals = {
        "commits": sum(day["commits"] for day in day_values),
        "issues": sum(day["issues"] for day in day_values),
        "pullRequests": sum(day["pullRequests"] for day in day_values),
    }

    return {
        "source": "github-search",
        "org": org,
        "user": user,
        "days": day_values,
        "totals": totals,
        "searchTotals": search_totals,
        "errors": errors,
    }


async def _search_items(
    client: GitHubClient,
    path: str,
    query: str,
    *,
    sort: str,
    max_pages: int = 5,
) -> dict[str, Any]:
    items = []
    total_count = 0
    incomplete = False
    try:
        for page in range(1, max_pages + 1):
            payload = await client.rest(
                "GET",
                path,
                {
                    "q": query,
                    "per_page": 100,
                    "page": page,
                    "sort": sort,
                    "order": "asc",
                },
            )
            page_items = payload.get("items") or []
            if page == 1:
                total_count = payload.get("total_count", 0)
            incomplete = incomplete or bool(payload.get("incomplete_results"))
            items.extend(page_items)
            if len(items) >= total_count or len(page_items) < 100:
                break
    except Exception as exc:
        return {
            "items": items,
            "totalCount": total_count,
            "incomplete": incomplete,
            "truncated": total_count > len(items),
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "items": items,
        "totalCount": total_count,
        "incomplete": incomplete,
        "truncated": total_count > len(items),
        "error": None,
    }


def _activity_date(kind: str, item: dict[str, Any]) -> str | None:
    if kind == "commits":
        commit = item.get("commit") or {}
        author = commit.get("author") or {}
        committer = commit.get("committer") or {}
        value = author.get("date") or committer.get("date")
    else:
        value = item.get("created_at")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


async def build_dashboard(
    client: GitHubClient,
    org: str,
    state: IssueState = "open",
    limit: int = 50,
    labels: str | None = None,
    repo: str | None = None,
    assignee: str | None = None,
    query: str | None = None,
    bot_login: str | None = None,
) -> dict[str, Any]:
    automation_bot = bot_login if bot_login is not None else settings.automation_bot_login
    bot_authors = _bot_author_logins(automation_bot)

    if bot_authors:
        issue_task = asyncio.gather(
            *[
                search_issues(
                    client,
                    org,
                    state=state,
                    limit=limit,
                    labels=labels,
                    repo=repo,
                    assignee=assignee,
                    author=author,
                    query=query,
                )
                for author in bot_authors
            ]
        )
        pr_task = asyncio.gather(
            *[
                search_pull_requests(
                    client,
                    org,
                    state="all",
                    limit=min(limit * 2, 100),
                    labels=None,
                    repo=repo,
                    author=author,
                    query=query,
                )
                for author in bot_authors
            ]
        )
    else:
        issue_task = search_issues(
            client,
            org,
            state=state,
            limit=limit,
            labels=labels,
            repo=repo,
            assignee=assignee,
            query=query,
        )
        pr_task = search_pull_requests(
            client,
            org,
            state="all",
            limit=min(limit * 2, 100),
            labels=None,
            repo=repo,
            query=query,
        )
    org_task = get_org(client, org)

    issue_result, pr_result, org_profile = await asyncio.gather(
        issue_task, pr_task, org_task
    )
    if bot_authors:
        issue_result = _merge_search_results(list(issue_result))
        pr_result = _merge_search_results(list(pr_result))

    incidents = _github_items_to_incidents(org, issue_result["items"], pr_result["items"])
    summary = _summarize(incidents, org_profile)

    return {
        "source": "github",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "tenant": org_profile,
        "tenants": [org_profile],
        "issues": issue_result,
        "pullRequests": pr_result,
        "filters": {
            "automationBot": automation_bot,
            "botAuthors": bot_authors,
            "issueState": state,
            "pullRequestState": "all",
        },
        "incidents": incidents,
        "summary": summary,
        "auditEvents": [
            {
                "id": "github-audit-unavailable",
                "tenantId": org,
                "type": "GitHub API",
                "actor": "backend",
                "detail": "Dashboard is populated from GitHub issues, PRs, checks, reviews, and repository metadata. Organization audit log access can be added separately for enterprise audit events.",
                "time": "Live",
            }
        ],
    }


async def get_issue_timeline(
    client: GitHubClient, owner: str, repo: str, number: int, per_page: int = 50
) -> list[dict[str, Any]]:
    events = await client.rest(
        "GET",
        f"/repos/{owner}/{repo}/issues/{number}/timeline",
        {"per_page": per_page},
    )
    return [
        {
            "id": event.get("id") or event.get("node_id"),
            "event": event.get("event"),
            "createdAt": event.get("created_at"),
            "actor": (event.get("actor") or {}).get("login"),
            "source": _timeline_source(event),
            "raw": event,
        }
        for event in events
    ]


async def get_pull_request_reviews(
    client: GitHubClient, owner: str, repo: str, number: int, per_page: int = 50
) -> list[dict[str, Any]]:
    reviews = await client.rest(
        "GET",
        f"/repos/{owner}/{repo}/pulls/{number}/reviews",
        {"per_page": per_page},
    )
    return [
        {
            "id": review.get("id"),
            "state": review.get("state"),
            "submittedAt": review.get("submitted_at"),
            "author": (review.get("user") or {}).get("login"),
            "url": review.get("html_url"),
            "body": review.get("body"),
        }
        for review in reviews
    ]


def _normalize_issue(node: dict[str, Any]) -> dict[str, Any]:
    labels = _labels(node)
    assignees = _users(node.get("assignees"))
    repository = node["repository"]
    return {
        "id": node["id"],
        "number": node["number"],
        "title": node["title"],
        "bodyText": node.get("bodyText") or "",
        "url": node["url"],
        "state": node["state"],
        "stateReason": node.get("stateReason"),
        "createdAt": node["createdAt"],
        "updatedAt": node["updatedAt"],
        "closedAt": node.get("closedAt"),
        "comments": node["comments"]["totalCount"],
        "repository": _repository(repository),
        "author": _actor(node.get("author")),
        "assignees": assignees,
        "labels": labels,
        "milestone": node.get("milestone"),
        "severity": _severity_from_labels(labels),
    }


def _normalize_pull_request(node: dict[str, Any]) -> dict[str, Any]:
    labels = _labels(node)
    checks = _checks(node)
    review_requests = []
    for item in (node.get("reviewRequests") or {}).get("nodes", []):
        reviewer = (item or {}).get("requestedReviewer") or {}
        review_requests.append(reviewer.get("login") or reviewer.get("slug") or reviewer.get("name"))
    review_requests = [item for item in review_requests if item]
    reviews = _reviews(node)
    reviewed_by = sorted({review["author"] for review in reviews if review.get("author")})

    return {
        "id": node["id"],
        "number": node["number"],
        "title": node["title"],
        "bodyText": node.get("bodyText") or "",
        "url": node["url"],
        "state": node["state"],
        "isDraft": node["isDraft"],
        "merged": node["merged"],
        "mergedAt": node.get("mergedAt"),
        "reviewDecision": node.get("reviewDecision"),
        "createdAt": node["createdAt"],
        "updatedAt": node["updatedAt"],
        "closedAt": node.get("closedAt"),
        "headRefName": node.get("headRefName"),
        "baseRefName": node.get("baseRefName"),
        "repository": _repository(node["repository"]),
        "author": _actor(node.get("author")),
        "assignees": _users(node.get("assignees")),
        "labels": labels,
        "reviewRequests": review_requests,
        "reviews": reviews,
        "reviewedBy": reviewed_by,
        "closingIssues": [
            {
                "number": issue["number"],
                "title": issue["title"],
                "url": issue["url"],
                "state": issue["state"],
                "repo": issue["repository"]["nameWithOwner"],
            }
            for issue in (node.get("closingIssuesReferences") or {}).get("nodes", [])
            if issue
        ],
        "checks": checks,
    }


def _github_items_to_incidents(
    org: str, issues: list[dict[str, Any]], pull_requests: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    prs_by_issue: dict[str, list[dict[str, Any]]] = {}
    for pr in pull_requests:
        for issue in pr.get("closingIssues", []):
            key = f"{issue['repo']}#{issue['number']}"
            prs_by_issue.setdefault(key, []).append(pr)

    incidents = []
    linked_pr_ids = set()
    for issue in issues:
        key = f"{issue['repository']['nameWithOwner']}#{issue['number']}"
        linked_prs = sorted(
            prs_by_issue.get(key, []),
            key=lambda item: item.get("updatedAt") or "",
            reverse=True,
        )
        primary_pr = linked_prs[0] if linked_prs else None
        linked_pr_ids.update(pr["id"] for pr in linked_prs)
        incidents.append(_incident_from_issue(org, issue, primary_pr, linked_prs))

    standalone_prs = [
        pr for pr in pull_requests
        if pr["id"] not in linked_pr_ids
    ]
    incidents.extend(_incident_from_pull_request(org, pr) for pr in standalone_prs)
    return sorted(
        incidents,
        key=lambda item: item.get("updatedAt") or item.get("startedAt") or "",
        reverse=True,
    )


def _incident_from_issue(
    org: str,
    issue: dict[str, Any],
    primary_pr: dict[str, Any] | None,
    linked_prs: list[dict[str, Any]],
) -> dict[str, Any]:
    labels = [label["name"] for label in issue["labels"]]
    issue_open = issue["state"] == "OPEN"
    pr_checks = primary_pr["checks"] if primary_pr else {"passing": 0, "total": 0, "failingName": None}
    status = _issue_status(issue, primary_pr, labels)
    assignees = _login_list(issue["assignees"])
    assignee = assignees[0] if assignees else (issue["author"] or {}).get("login")
    elapsed = _elapsed(issue["createdAt"], issue.get("closedAt"))
    updated_values = [
        value
        for value in [issue.get("updatedAt"), primary_pr.get("updatedAt") if primary_pr else None]
        if value
    ]

    return {
        "id": f"GH-{issue['repository']['name']}-{issue['number']}",
        "sourceType": "issue",
        "tenantId": org,
        "issue": issue["number"],
        "issueUrl": issue["url"],
        "pr": primary_pr["number"] if primary_pr else None,
        "prUrl": primary_pr["url"] if primary_pr else None,
        "linkedPullRequests": linked_prs,
        "title": issue["title"],
        "severity": issue["severity"],
        "status": status,
        "health": "active" if issue_open else "stabilizing",
        "service": issue["repository"]["name"],
        "repo": issue["repository"]["nameWithOwner"],
        "branch": primary_pr["headRefName"] if primary_pr else "No remediation branch",
        "owner": issue["repository"]["owner"],
        "author": (issue["author"] or {}).get("login"),
        "assignee": assignee or "unassigned",
        "assignees": assignees,
        "startedAt": issue["createdAt"],
        "updatedAt": max(updated_values) if updated_values else issue["createdAt"],
        "elapsed": elapsed,
        "confidence": _confidence(issue, primary_pr),
        "impact": _issue_impact(issue),
        "agentSummary": _agent_summary(issue, primary_pr),
        "mcpCalls": _github_data_points(primary_pr),
        "checks": pr_checks,
        "reviewers": primary_pr["reviewRequests"] if primary_pr else [],
        "reviewedBy": primary_pr.get("reviewedBy", []) if primary_pr else [],
        "labels": labels,
        "timeline": _timeline_from_github(issue, primary_pr, labels),
    }


def _incident_from_pull_request(org: str, pr: dict[str, Any]) -> dict[str, Any]:
    labels = [label["name"] for label in pr["labels"]]
    linked_issue = pr["closingIssues"][0] if pr.get("closingIssues") else None
    pr_closed_at = pr.get("mergedAt") or pr.get("closedAt")
    assignees = _login_list(pr["assignees"])
    assignee = assignees[0] if assignees else (pr["author"] or {}).get("login")
    pr_open = pr["state"] == "OPEN"

    return {
        "id": f"GH-PR-{pr['repository']['name']}-{pr['number']}",
        "sourceType": "pull_request",
        "tenantId": org,
        "issue": linked_issue["number"] if linked_issue else None,
        "issueUrl": linked_issue["url"] if linked_issue else None,
        "pr": pr["number"],
        "prUrl": pr["url"],
        "linkedPullRequests": [pr],
        "title": pr["title"],
        "severity": _severity_from_labels(pr["labels"]),
        "status": _pull_request_status(pr),
        "health": "active" if pr_open and not pr["merged"] else "stabilizing",
        "service": pr["repository"]["name"],
        "repo": pr["repository"]["nameWithOwner"],
        "branch": pr.get("headRefName") or "Unknown branch",
        "owner": pr["repository"]["owner"],
        "author": (pr["author"] or {}).get("login"),
        "assignee": assignee or "unassigned",
        "assignees": assignees,
        "startedAt": pr["createdAt"],
        "updatedAt": pr["updatedAt"],
        "elapsed": _elapsed(pr["createdAt"], pr_closed_at),
        "confidence": _pull_request_confidence(pr),
        "impact": _pull_request_impact(pr),
        "agentSummary": _pull_request_summary(pr),
        "mcpCalls": [
            "search_pull_requests",
            "list_review_requests",
            "list_pull_request_reviews",
            "list_check_runs",
        ],
        "checks": pr["checks"],
        "reviewers": pr["reviewRequests"],
        "reviewedBy": pr.get("reviewedBy", []),
        "labels": labels,
        "timeline": _timeline_from_pull_request(pr),
    }


def _issue_status(
    issue: dict[str, Any], primary_pr: dict[str, Any] | None, labels: list[str]
) -> str:
    normalized = {label.lower() for label in labels}
    if issue["state"] == "CLOSED":
        return "Issue closed"
    if any("approval" in label for label in normalized):
        return "Review requested"
    if not primary_pr:
        return "Open issue"
    if primary_pr["merged"]:
        return "PR merged"
    if primary_pr["isDraft"]:
        return "Draft PR"
    if primary_pr["checks"]["failingName"]:
        return "Checks failing"
    return "Linked PR open"


def _pull_request_status(pr: dict[str, Any]) -> str:
    decision = pr.get("reviewDecision")
    if pr["merged"]:
        return "PR merged"
    if pr["state"] == "CLOSED":
        return "PR closed"
    if pr["isDraft"]:
        return "Draft PR"
    if pr["checks"]["failingName"]:
        return "Checks failing"
    if decision == "APPROVED":
        return "Review approved"
    if decision == "CHANGES_REQUESTED":
        return "Changes requested"
    if decision == "REVIEW_REQUIRED" or pr["reviewRequests"]:
        return "Review requested"
    return "PR open"


def _timeline_from_github(
    issue: dict[str, Any], primary_pr: dict[str, Any] | None, labels: list[str]
) -> list[dict[str, str]]:
    issue_done = issue["state"] == "CLOSED"
    pr_exists = primary_pr is not None
    checks = primary_pr["checks"] if primary_pr else {"passing": 0, "total": 0, "failingName": None}
    check_status = "waiting"
    if checks["total"]:
        check_status = "blocked" if checks["failingName"] else "done"

    return [
        {
            "stage": "Issue",
            "status": "done" if issue_done else "current",
            "actor": "GitHub Issue",
            "detail": _issue_timeline_detail(issue, labels),
            "time": _short_time(issue["updatedAt"]),
        },
        {
            "stage": "Linked PR",
            "status": "done" if primary_pr and primary_pr["merged"] else ("current" if pr_exists else "waiting"),
            "actor": "GitHub Pull Request",
            "detail": _pr_detail(primary_pr),
            "time": _short_time(primary_pr["updatedAt"]) if primary_pr else "Pending",
        },
        {
            "stage": "Review",
            "status": _review_status(primary_pr),
            "actor": "Review Decision",
            "detail": _review_detail(primary_pr),
            "time": _short_time(primary_pr["updatedAt"]) if primary_pr else "Pending",
        },
        {
            "stage": "Checks",
            "status": check_status,
            "actor": "GitHub Checks",
            "detail": _checks_detail(checks),
            "time": _short_time(primary_pr["updatedAt"]) if primary_pr else "Pending",
        },
        {
            "stage": "Merge / Closure",
            "status": "done" if issue_done and (not primary_pr or primary_pr["merged"]) else ("current" if primary_pr and primary_pr["merged"] else "waiting"),
            "actor": "GitHub State",
            "detail": _closure_detail(issue, primary_pr),
            "time": _short_time(issue.get("closedAt") or (primary_pr or {}).get("mergedAt")),
        },
    ]


def _timeline_from_pull_request(pr: dict[str, Any]) -> list[dict[str, str]]:
    linked_issue = pr["closingIssues"][0] if pr.get("closingIssues") else None
    checks = pr["checks"]
    check_status = "waiting"
    if checks["total"]:
        check_status = "blocked" if checks["failingName"] else "done"

    if pr["merged"]:
        closure_status = "done"
    elif pr["state"] == "CLOSED":
        closure_status = "blocked"
    else:
        closure_status = "waiting"

    return [
        {
            "stage": "Issue",
            "status": "done" if linked_issue else "waiting",
            "actor": "Closing Issue Reference",
            "detail": _linked_issue_detail(linked_issue),
            "time": _short_time(pr["updatedAt"]) if linked_issue else "Pending",
        },
        {
            "stage": "Linked PR",
            "status": "done" if pr["merged"] else ("current" if pr["state"] == "OPEN" else "blocked"),
            "actor": "GitHub Pull Request",
            "detail": _pr_detail(pr),
            "time": _short_time(pr["updatedAt"]),
        },
        {
            "stage": "Review",
            "status": _review_status(pr),
            "actor": "Review Decision",
            "detail": _review_detail(pr),
            "time": _short_time(pr["updatedAt"]),
        },
        {
            "stage": "Checks",
            "status": check_status,
            "actor": "GitHub Checks",
            "detail": _checks_detail(checks),
            "time": _short_time(pr["updatedAt"]) if checks["total"] else "Pending",
        },
        {
            "stage": "Merge / Closure",
            "status": closure_status,
            "actor": "GitHub State",
            "detail": _pull_request_closure_detail(pr, linked_issue),
            "time": _short_time(pr.get("mergedAt") or pr.get("closedAt")),
        },
    ]


def _labels(node: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": label["name"],
            "color": label.get("color"),
            "description": label.get("description"),
        }
        for label in (node.get("labels") or {}).get("nodes", [])
        if label
    ]


def _users(connection: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [_actor(user) for user in (connection or {}).get("nodes", []) if user]


def _login_list(users: list[dict[str, Any] | None]) -> list[str]:
    return [user["login"] for user in users if user and user.get("login")]


def _actor(actor: dict[str, Any] | None) -> dict[str, Any] | None:
    if not actor:
        return None
    return {
        "login": actor.get("login"),
        "url": actor.get("url"),
        "avatarUrl": actor.get("avatarUrl"),
    }


def _repository(repo: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": repo["name"],
        "nameWithOwner": repo["nameWithOwner"],
        "owner": repo["owner"]["login"],
        "url": repo["url"],
        "private": repo["isPrivate"],
    }


def _reviews(node: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "state": review.get("state"),
            "submittedAt": review.get("submittedAt"),
            "author": (review.get("author") or {}).get("login"),
        }
        for review in (node.get("reviews") or {}).get("nodes", [])
        if review
    ]


def _checks(pr: dict[str, Any]) -> dict[str, Any]:
    commit_nodes = (pr.get("commits") or {}).get("nodes", [])
    if not commit_nodes:
        return {"passing": 0, "total": 0, "failingName": None, "rollupState": None, "contexts": []}
    rollup = ((commit_nodes[-1] or {}).get("commit") or {}).get("statusCheckRollup")
    if not rollup:
        return {"passing": 0, "total": 0, "failingName": None, "rollupState": None, "contexts": []}

    contexts = []
    passing = 0
    failing_name = None
    for context in (rollup.get("contexts") or {}).get("nodes", []):
        if not context:
            continue
        name = context.get("name") or context.get("context") or "check"
        status = context.get("status") or context.get("state")
        conclusion = context.get("conclusion") or context.get("state")
        normalized = (conclusion or status or "").upper()
        contexts.append(
            {
                "name": name,
                "status": status,
                "conclusion": conclusion,
                "url": context.get("detailsUrl") or context.get("targetUrl"),
            }
        )
        if normalized in {"SUCCESS", "NEUTRAL", "SKIPPED", "EXPECTED"}:
            passing += 1
        elif normalized in {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"} and not failing_name:
            failing_name = name

    return {
        "passing": passing,
        "total": len(contexts),
        "failingName": failing_name,
        "rollupState": rollup.get("state"),
        "contexts": contexts,
    }


def _severity_from_labels(labels: list[dict[str, Any]]) -> str:
    normalized = [label["name"].lower().replace("_", "-").replace(" ", "-") for label in labels]
    for sev in ("sev-0", "sev0", "severity-0", "severity:p0"):
        if sev in normalized:
            return "SEV-0"
    for sev in ("sev-1", "sev1", "severity-1", "severity:p1", "critical"):
        if sev in normalized:
            return "SEV-1"
    for sev in ("sev-2", "sev2", "severity-2", "severity:p2", "high"):
        if sev in normalized:
            return "SEV-2"
    return "SEV-3"


def _confidence(issue: dict[str, Any], primary_pr: dict[str, Any] | None) -> int:
    score = 55
    if issue["labels"]:
        score += 10
    if issue["comments"]:
        score += min(issue["comments"], 10)
    if primary_pr:
        score += 15
    if primary_pr and primary_pr["checks"]["total"]:
        score += 8
    return min(score, 96)


def _pull_request_confidence(pr: dict[str, Any]) -> int:
    score = 60
    if pr["reviewRequests"]:
        score += 10
    if pr["reviews"]:
        score += 10
    if pr["checks"]["total"]:
        score += 10
    if pr["closingIssues"]:
        score += 8
    return min(score, 96)


def _issue_impact(issue: dict[str, Any]) -> str:
    body = (issue.get("bodyText") or "").strip().splitlines()
    if body:
        return body[0][:180]
    return "Impact details are not available in the issue body yet."


def _pull_request_impact(pr: dict[str, Any]) -> str:
    body = (pr.get("bodyText") or "").strip().splitlines()
    if body:
        return body[0][:180]
    if pr["closingIssues"]:
        issue = pr["closingIssues"][0]
        return f"Linked to issue #{issue['number']}: {issue['title']}"
    return "This bot-created PR is not linked to an issue through closing issue references."


def _agent_summary(issue: dict[str, Any], primary_pr: dict[str, Any] | None) -> str:
    if primary_pr:
        return f"GitHub has a linked remediation PR #{primary_pr['number']} for this issue. Review decision: {primary_pr.get('reviewDecision') or 'not set'}."
    return "No linked remediation PR was found through GitHub closing issue references."


def _pull_request_summary(pr: dict[str, Any]) -> str:
    author = (pr["author"] or {}).get("login") or "unknown"
    decision = pr.get("reviewDecision") or "not set"
    return f"Bot-authored PR #{pr['number']} by {author}. Review decision: {decision}."


def _github_data_points(primary_pr: dict[str, Any] | None) -> list[str]:
    calls = ["search_issues", "list_issue_labels", "list_issue_assignees"]
    if primary_pr:
        calls.extend(["search_pull_requests", "list_check_runs", "list_pull_request_reviews"])
    return calls


def _issue_timeline_detail(issue: dict[str, Any], labels: list[str]) -> str:
    state = issue["state"].lower()
    assignees = ", ".join(user["login"] for user in issue["assignees"]) or "unassigned"
    label_text = ", ".join(labels[:3]) if labels else "no labels"
    return f"Issue #{issue['number']} is {state}; assignee: {assignees}; labels: {label_text}."


def _linked_issue_detail(linked_issue: dict[str, Any] | None) -> str:
    if not linked_issue:
        return "No closing issue reference was returned for this bot-created PR."
    return f"PR references issue #{linked_issue['number']}: {linked_issue['title']}."


def _review_status(primary_pr: dict[str, Any] | None) -> str:
    if not primary_pr:
        return "waiting"
    decision = primary_pr.get("reviewDecision")
    if decision == "APPROVED":
        return "done"
    if decision == "CHANGES_REQUESTED":
        return "blocked"
    if decision == "REVIEW_REQUIRED" or primary_pr["reviewRequests"]:
        return "current"
    return "waiting"


def _review_detail(primary_pr: dict[str, Any] | None) -> str:
    if not primary_pr:
        return "No pull request review data is available yet."
    reviewers = ", ".join(primary_pr["reviewRequests"])
    decision = primary_pr.get("reviewDecision") or "not set"
    if reviewers:
        return f"Review decision is {decision}; requested reviewers: {reviewers}."
    return f"Review decision is {decision}; no requested reviewers were returned."


def _pr_detail(primary_pr: dict[str, Any] | None) -> str:
    if not primary_pr:
        return "Waiting for an agent-created remediation pull request."
    return f"PR #{primary_pr['number']} is {primary_pr['state'].lower()} on branch {primary_pr.get('headRefName') or 'unknown'}."


def _checks_detail(checks: dict[str, Any]) -> str:
    if not checks["total"]:
        return "No check runs or commit statuses were found on the linked PR."
    if checks["failingName"]:
        return f"{checks['failingName']} is failing."
    return f"{checks['passing']} of {checks['total']} checks are passing."


def _closure_detail(issue: dict[str, Any], primary_pr: dict[str, Any] | None) -> str:
    issue_state = issue["state"].lower()
    if not primary_pr:
        return f"Issue is {issue_state}; no linked PR is available."
    pr_state = "merged" if primary_pr["merged"] else primary_pr["state"].lower()
    return f"PR #{primary_pr['number']} is {pr_state}; issue is {issue_state}."


def _pull_request_closure_detail(
    pr: dict[str, Any], linked_issue: dict[str, Any] | None
) -> str:
    pr_state = "merged" if pr["merged"] else pr["state"].lower()
    if not linked_issue:
        return f"PR #{pr['number']} is {pr_state}; no linked issue state is available."
    return f"PR #{pr['number']} is {pr_state}; linked issue #{linked_issue['number']} is {linked_issue['state'].lower()}."


def _summarize(incidents: list[dict[str, Any]], org_profile: dict[str, Any]) -> dict[str, Any]:
    active = sum(1 for incident in incidents if incident["health"] == "active")
    prs = sum(1 for incident in incidents if incident["pr"])
    approvals = sum(1 for incident in incidents if "approval" in incident["status"].lower())
    failing = sum(1 for incident in incidents if incident["checks"]["failingName"])
    return {
        "activeIncidents": active,
        "agentCreatedPullRequests": prs,
        "approvalGates": approvals,
        "failingChecks": failing,
        "repositories": org_profile.get("repositories", 0),
    }


def _timeline_source(event: dict[str, Any]) -> dict[str, Any] | None:
    source = event.get("source") or {}
    issue = source.get("issue")
    if not issue:
        return None
    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "url": issue.get("html_url"),
        "isPullRequest": bool(issue.get("pull_request")),
    }


def _elapsed(start: str, end: str | None = None) -> str:
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else datetime.now(timezone.utc)
        minutes = max(int((end_dt - start_dt).total_seconds() // 60), 0)
    except (TypeError, ValueError):
        return "Unknown"
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    remaining = minutes % 60
    return f"{hours}h {remaining}m"


def _short_time(value: str | None) -> str:
    if not value:
        return "Pending"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%H:%M")
    except ValueError:
        return value

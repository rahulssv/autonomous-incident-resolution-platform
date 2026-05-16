# Backend: AIR GitHub API

FastAPI backend for the Autonomous Incident Resolution dashboard. It handles GitHub OAuth sign-in, stores a local browser session, calls GitHub APIs with the signed-in user token, and returns normalized dashboard data to the React UI.

## What This Backend Does

- Handles GitHub OAuth web sign-in.
- Stores the GitHub user token in an in-memory, signed, HTTP-only session cookie.
- Discovers GitHub organizations and GitHub App organization installations, then exposes them as tenants.
- Reads GitHub issues across an org.
- Reads linked pull requests, review requests, reviews, checks, labels, and closing issue references.
- Aggregates bot-authored GitHub issue/PR data into a dashboard-friendly incident model.
- Reads per-user GitHub activity for Analytics: issues opened, pull requests opened, and commits authored.
- Streams resolution graph progress events for the Resolution Console.
- Provides diagnostics for OAuth/org visibility issues.

## What This Backend Does Not Do Yet

- It does not create PRs. Agents/MCP will create PRs later.
- It does not run remediation workflows.
- It does not call GitHub MCP directly.
- It does not enforce real RBAC yet.
- It does not store sessions in Redis/database yet. Sessions are in memory and reset when the backend restarts.
- It does not read real telemetry from Prometheus/Grafana yet.
- It does not read GitHub Enterprise audit logs yet.

## File Map

```text
backend/
|-- app/
|   |-- main.py              FastAPI app, CORS, route registration, GitHub endpoints
|   |-- auth.py              GitHub OAuth login/callback/session/logout/org diagnostics
|   |-- config.py            Environment variable loading and settings
|   |-- github_client.py     Thin async GitHub REST/GraphQL client
|   |-- github_queries.py    GraphQL queries for issues, PRs, viewer/orgs
|   |-- github_service.py    Normalization and dashboard aggregation logic
|   `-- http_client.py       Shared HTTPX TLS/proxy settings
|-- requirements.txt
|-- .env.example
`-- oauth-debug.log          Created only when OAuth/debug errors are logged
```

## Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Run:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## Environment Variables

| Variable | Purpose |
|---|---|
| `GITHUB_OAUTH_CLIENT_ID` | GitHub OAuth App client id, or GitHub App client id when OAuth is enabled on a GitHub App |
| `GITHUB_OAUTH_CLIENT_SECRET` | GitHub OAuth App client secret, or GitHub App client secret |
| `GITHUB_OAUTH_REDIRECT_URI` | Must match GitHub OAuth callback URL |
| `GITHUB_OAUTH_SCOPES` | Comma-separated scopes, defaults to `read:user,user:email,read:org,repo` |
| `FRONTEND_URL` | Frontend return URL after OAuth |
| `SESSION_SECRET` | Signs local session cookies |
| `SESSION_COOKIE_NAME` | Defaults to `air_session` |
| `SESSION_COOKIE_SECURE` | Set `true` for HTTPS deployments |
| `SESSION_TTL_SECONDS` | Session lifetime |
| `GITHUB_TOKEN` | Optional fallback token for backend-only testing |
| `GITHUB_API_VERSION` | GitHub REST API version |
| `GITHUB_BASE_URL` | GitHub REST base URL |
| `GITHUB_GRAPHQL_URL` | GitHub GraphQL URL |
| `GITHUB_USE_SYSTEM_CERT_STORE` | Uses Windows/system CA store through `truststore` |
| `GITHUB_SSL_VERIFY` | Keep `true`; set `false` only for local debugging |
| `CORS_ORIGINS` | Allowed frontend origins |
| `GITHUB_ISSUE_LABEL_FILTER` | Optional issue label filter for dashboard searches |
| `GITHUB_AUTOMATION_BOT_LOGIN` | Automation bot used for dashboard scoping. Defaults to `airp-automation-bot` |
| `GITHUB_AGENT_PR_LABEL_FILTER` | Reserved for agent-created PR label detection |

## GitHub OAuth Flow

1. UI calls `GET /api/auth/me`.
2. If not logged in, UI redirects to `GET /api/auth/github/login`.
3. Backend creates an OAuth `state`, stores it in memory, sets a signed state cookie, and redirects to GitHub.
4. GitHub redirects to `GET /api/auth/github/callback`.
5. Backend verifies the state cookie and query param.
6. Backend exchanges the code at GitHub's OAuth token endpoint.
7. Backend calls GitHub APIs to read viewer/org data. For GitHub App user tokens, it also reads `/user/installations` because GitHub App user tokens use app permissions instead of OAuth scopes.
8. Backend stores the token and user profile in an in-memory session.
9. Backend sets `air_session` HTTP-only cookie and redirects to the frontend.

## Token Selection

For GitHub API calls, `main.py` uses this priority:

1. `Authorization: Bearer ...` header
2. OAuth session cookie token
3. `GITHUB_TOKEN` from `.env`

This means frontend browser requests normally use the OAuth session token, while terminal/API tests can use `GITHUB_TOKEN`.

## Backend Endpoints

### Health

`GET /api/health`

Returns backend status and whether OAuth/PAT config exists.

### Auth

`GET /api/auth/github/login`

Starts GitHub OAuth. Called by the frontend sign-in button.

`GET /api/auth/github/callback`

GitHub redirects here after authorization. Not called manually.

`GET /api/auth/me`

Returns current browser session, user profile, GitHub organizations or GitHub App organization installations, token scope information, and org count. Called by the frontend on app load. It refreshes organizations on each call.

`GET /api/auth/org-debug`

Diagnostic endpoint for org visibility. It checks:

- GraphQL viewer organizations
- REST `/user/orgs`
- REST `/user/memberships/orgs`
- REST `/user/installations`

Use this when tenants are missing.

`POST /api/auth/logout`

Clears local session cookie and in-memory session.

### GitHub Viewer/Org

`GET /api/github/me`

Returns normalized GitHub viewer profile and orgs.

`GET /api/github/orgs`

Returns organizations for the current GitHub token.

`GET /api/github/orgs/{org}`

Returns organization profile from GitHub REST.

`GET /api/github/orgs/{org}/repos`

Returns repositories for the org from GitHub REST.

### GitHub Issues And Pull Requests

`GET /api/github/orgs/{org}/issues`

GraphQL search for cross-repository issues. Query params:

- `state=open|closed|all`
- `limit=1..100`
- `labels=incident,sev-1`
- `repo=repo-name`
- `assignee=login`
- `author=login`
- `q=extra GitHub search terms`

`GET /api/github/orgs/{org}/pull-requests`

GraphQL search for PRs. Query params:

- `state=open|closed|all`
- `limit=1..100`
- `labels=...`
- `repo=...`
- `assignee=...`
- `author=...`
- `q=...`

`GET /api/github/orgs/{org}/dashboard`

Main endpoint consumed by the UI after tenant selection. It:

- Gets org profile.
- Searches issues authored by the configured automation bot.
- Searches PRs authored by the configured automation bot.
- Searches both bot author forms: `author:{bot}` and `author:app/{bot}`.
- Links PRs to issues using `closingIssuesReferences`.
- Builds issue rows and standalone PR rows.
- Returns GitHub source data plus UI-ready `incidents`.

Optional query params:

- `state=open|closed|all`
- `limit=1..100`
- `labels=...`
- `repo=...`
- `assignee=...`
- `bot=...` to override `GITHUB_AUTOMATION_BOT_LOGIN`
- `q=...`

`GET /api/github/orgs/{org}/user-activity`

Returns daily activity counts for one GitHub login in the selected organization. Query params:

- `user=login`
- `days=1..31`, defaults to `21`

The endpoint uses GitHub search APIs over the requested date range and groups results by day:

- issues created by the user
- pull requests created by the user
- commits authored by the user

The React Analytics tab calls this endpoint for the signed-in user and renders the grouped bar chart.

`GET /api/github/repos/{owner}/{repo}/issues/{number}/timeline`

Reads issue timeline from GitHub REST. Not currently called by UI.

`GET /api/github/repos/{owner}/{repo}/pulls/{number}/reviews`

Reads PR reviews from GitHub REST. Not currently called by UI.

`GET /api/github/rate-limit`

Returns GitHub API rate limit data. Not currently called by UI.

### Resolution Graph

`GET /api/graph/stages`

Returns the ordered graph nodes used by the Resolution Console horizontal stepper.

`GET /api/graph/incidents`

Returns unresolved graph incidents for the Resolution Console queue. This is currently dummy in-memory data in `app/graph_service.py`. The frontend polls this endpoint so newly detected unresolved incidents can appear without a page refresh.

`GET /api/graph/incidents/{incident_id}`

Returns per-incident graph state for the selected unresolved incident, including current node, completed nodes, detection details, RCA evidence, documentation draft, and issue creation state.

`GET /api/graph/incidents/{incident_id}/stream`

Streams server-sent events for one selected incident. The frontend updates the horizontal stepper from `stage_completed` events. When the stream completes and a GitHub issue is created, the incident is removed from the unresolved queue on the next poll. In the real integration, that new issue should then appear in the GitHub-backed Incidents tab after dashboard refresh.

`GET /api/graph/demo-resolution`

Streams server-sent events that match the standalone prototype and future LangGraph/sub-agent progress shape. Query params:

- `scenario=crashloop|oom|latency`
- `severity=critical|warning|info`
- `title=optional incident title`

Events emitted:

- `metadata`
- `run_started`
- `stage_completed`
- `run_completed`
- `resolution_error` for future error paths

The current implementation in `app/graph_service.py` is a demo adapter. When the real LangGraph runner is available, keep the same event contract and emit `stage_completed` when each LangGraph node or sub-agent finishes. The frontend marks completed nodes green from those events.

## GitHub APIs Used Internally

| Backend area | GitHub API |
|---|---|
| OAuth code exchange | `POST https://github.com/login/oauth/access_token` |
| Viewer/orgs | GraphQL `viewer { organizations }` |
| Org fallback | REST `GET /user/orgs` |
| Org membership fallback | REST `GET /user/memberships/orgs` |
| GitHub App tenant fallback | REST `GET /user/installations` |
| Org profile | REST `GET /orgs/{org}` |
| Repos | REST `GET /orgs/{org}/repos` |
| Issues | GraphQL `search(type: ISSUE, query: "org:{org} is:issue ...")` |
| Pull requests | GraphQL `search(type: ISSUE, query: "org:{org} is:pr ...")` |
| User activity issues/PRs | REST `GET /search/issues` |
| User activity commits | REST `GET /search/commits` |
| Resolution graph stages | Local graph adapter `GET /api/graph/stages` |
| Resolution unresolved incidents | Local graph adapter `GET /api/graph/incidents` |
| Resolution incident detail | Local graph adapter `GET /api/graph/incidents/{incident_id}` |
| Resolution graph progress | SSE `GET /api/graph/incidents/{incident_id}/stream` |
| Issue timeline | REST `GET /repos/{owner}/{repo}/issues/{number}/timeline` |
| PR reviews | REST `GET /repos/{owner}/{repo}/pulls/{number}/reviews` |

## Dashboard Data Shape

The dashboard endpoint returns:

```json
{
  "source": "github",
  "tenant": {},
  "tenants": [],
  "issues": {},
  "pullRequests": {},
  "incidents": [],
  "summary": {},
  "auditEvents": []
}
```

Tenants come from GitHub organizations and, when a GitHub App user access token is used, organization installations visible at `/user/installations`.

`incidents` are derived from bot-authored GitHub issues and bot-authored PRs. Linked PRs are attached to issue rows when GitHub returns `closingIssuesReferences`; bot PRs without a returned issue are shown as standalone PR rows. The visible incident view is limited to GitHub-backed fields:

- `labels` from GitHub issue labels
- `status` from issue/PR/check/review state
- `timeline` with five steps: Issue, Linked PR, Review, Checks, and Merge / Closure
- `checks` from the latest PR commit status/check rollup
- `reviewers` from PR review requests
- `assignees` and `reviewedBy` for frontend user scoping

The React UI applies role scoping after this payload loads:

- Admin: all bot-authored issue/PR rows for the selected tenant.
- User: rows where the signed-in GitHub login is in `assignee`, `assignees`, `reviewers`, or `reviewedBy`.

Fields that remain in the API but are not shown in the dashboard yet:

- `mcpCalls` backend read names. These are internal evidence labels, not real MCP event logs, so the UI hides them.

The user activity endpoint returns:

```json
{
  "source": "github-search",
  "org": "example-org",
  "user": "octocat",
  "days": [
    {
      "date": "2026-05-16",
      "label": "Sat 05/16",
      "commits": 3,
      "issues": 1,
      "pullRequests": 2
    }
  ],
  "totals": {
    "commits": 3,
    "issues": 1,
    "pullRequests": 2
  },
  "searchTotals": {},
  "errors": []
}
```

`errors` can contain partial GitHub search failures, including missing commit search access or truncated results. The frontend still renders the counts that were available.

## Placeholder And Future Work

| Area | Current behavior | Future integration |
|---|---|---|
| Agent PR creation | Not done by backend | Agent/GitHub MCP creates PRs |
| Agent workflow events | Not shown as workflow stages yet | Persist agent events and show real process state |
| Telemetry | Not shown in the workflow yet | Prometheus/Grafana/OpenTelemetry API |
| RCA, recovery, docs | Removed from workflow until backed by real data | Agent RCA logs, deployment telemetry, docs publishing events |
| RBAC | Frontend toggle | Backend roles/claims and route enforcement |
| Session store | In memory | Redis or database |
| Audit events | Placeholder | GitHub Enterprise audit log / internal audit service |
| Tenant model | GitHub orgs | Add DB-backed tenant metadata if needed |
| GitHub App auth | Uses user access token and installation tenant discovery | Add installation-token flow for server-side agent actions if needed |

## Troubleshooting

### Sign-in succeeds but no tenants appear

Open:

```text
http://127.0.0.1:8000/api/auth/org-debug
```

Check:

- For OAuth Apps, `sessionScope` includes `read:org`
- `checks.user_orgs.count`
- `checks.user_memberships.count`
- For GitHub Apps, `checks.user_installations.count`

If counts are `0`, possible causes:

- The GitHub account is not a member of any organization.
- The org restricts OAuth apps and the app needs org-owner approval.
- The app was authorized before scope changes. Revoke it under GitHub user settings and sign in again.
- For GitHub Apps, the app is not installed on the organization, this user has not authorized the app, or the installation is only on a personal account instead of an organization.

GitHub App user access tokens normally return an empty `scope` value. That is expected because GitHub Apps use fine-grained app permissions rather than OAuth scopes.

### Python cannot reach GitHub OAuth endpoint

If logs show `CERTIFICATE_VERIFY_FAILED`, keep:

```env
GITHUB_USE_SYSTEM_CERT_STORE=true
GITHUB_SSL_VERIFY=true
```

The backend uses `truststore` so Python/httpx can use the OS certificate store on Windows.

### OAuth callback shows invalid state

Start the login again from the frontend button. GitHub OAuth codes and state values are single-use.

## Security Notes

- Do not commit `.env`.
- Rotate OAuth client secret if it is exposed.
- In production, use HTTPS and `SESSION_COOKIE_SECURE=true`.
- Replace in-memory sessions with Redis/database.
- Do not set `GITHUB_SSL_VERIFY=false` outside local debugging.

## Verification

```powershell
cd backend
.\.venv\Scripts\python.exe -m compileall app
.\.venv\Scripts\python.exe -c "from app.main import app; print(app.title)"
```

Health:

```text
http://127.0.0.1:8000/api/health
```

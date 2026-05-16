# Autonomous Incident Resolution Dashboard

React + Python prototype for an Autonomous Incident Resolution Platform. The UI is role-aware and reads GitHub organization, GitHub App installation, issue, pull request, check, review, and timeline data through the backend. Agent-created remediation PRs and incident telemetry are still represented as placeholders until the agent/MCP layer is connected.

## Project Layout

```text
.
|-- src/                    React dashboard
|   |-- App.jsx             Main UI, views, RBAC toggle, tenant selector
|   |-- api.js              Frontend API client for auth + dashboard data
|   |-- mockGithubData.js   Mock fallback data and placeholder incident model
|   `-- App.css             Dashboard styling
|-- backend/                FastAPI backend
|   |-- app/auth.py         GitHub OAuth session flow
|   |-- app/main.py         API routes
|   |-- app/github_client.py
|   |-- app/github_service.py
|   |-- app/github_queries.py
|   `-- app/http_client.py
`-- diagram-export-...png   Architecture reference image used by UI
```

## Runtime Flow

1. User opens the React app at `http://127.0.0.1:5173`.
2. Frontend calls `GET /api/auth/me`.
3. If unauthenticated, user clicks **Continue with GitHub**.
4. Frontend redirects to `GET /api/auth/github/login`.
5. Backend redirects to GitHub OAuth.
6. GitHub redirects back to `GET /api/auth/github/callback`.
7. Backend exchanges the OAuth code for a GitHub token and stores it in a local signed HTTP-only session cookie.
8. Frontend calls `GET /api/auth/me` again.
9. Backend uses the session token to discover GitHub organizations. For GitHub App user tokens, it also checks app installations through `/user/installations`. These organizations become tenants.
10. For the selected tenant/org, frontend calls `GET /api/github/orgs/{org}/dashboard`.
11. The backend filters dashboard data to issues and PRs authored by `GITHUB_AUTOMATION_BOT_LOGIN`, defaulting to `airp-automation-bot`.
12. The Analytics tab also calls `GET /api/github/orgs/{org}/user-activity` for the signed-in user and renders daily issues vs commits vs pull requests.

## Frontend

Install and run:

```bash
npm install
npm run dev
```

Default backend URL:

```text
http://127.0.0.1:8000
```

Override:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

### Frontend Files

`src/App.jsx`

- Renders sign-in screen.
- Checks current OAuth session.
- Builds tenant dropdown from GitHub organizations returned by backend.
- Renders Admin and User views.
- Shows resolution console, incidents, PR tracking, analytics, and architecture tabs.
- Shows a no-tenant state when GitHub returns no orgs.

`src/resolution-prototype/`

- Archived copy of the standalone HTML/CSS/JS prototype.
- The active implementation is converted into React inside `src/App.jsx` with scoped styles in `src/App.css`.

`src/api.js`

- Contains all frontend-to-backend calls.
- Starts GitHub login redirect.
- Reads auth session.
- Logs out.
- Loads dashboard data for selected GitHub org.
- Loads signed-in user activity for the Analytics bar chart.
- Converts auth organizations into UI tenants.

`src/mockGithubData.js`

- Mock fallback data only.
- Used before login or if backend data cannot be loaded.
- Contains placeholder incidents, PRs, labels, reviews, checks, and audit events for the pre-login fallback screen.

## UI To Backend API Calls

| UI action | Frontend function | Backend endpoint | Status |
|---|---|---|---|
| App loads | `fetchAuthSession()` | `GET /api/auth/me` | Real |
| Continue with GitHub | `beginGitHubLogin()` | `GET /api/auth/github/login` | Real |
| GitHub redirects back | Browser redirect | `GET /api/auth/github/callback` | Real |
| Sign out | `logout()` | `POST /api/auth/logout` | Real |
| Resolution tab loads | `fetchResolutionStages()` | `GET /api/graph/stages` | Real endpoint with graph node/stage metadata |
| Resolution queue polls | `fetchResolutionIncidents()` | `GET /api/graph/incidents` | Dummy unresolved LangGraph incidents for now |
| Resolution incident selected | `fetchResolutionIncident(id)` | `GET /api/graph/incidents/{id}` | Dummy per-incident graph state for now |
| Run selected incident | `EventSource` stream | `GET /api/graph/incidents/{id}/stream` | Server-sent node progress events; demo adapter until real LangGraph/sub-agent runner is connected |
| Tenant dashboard loads | `fetchDashboardData(org, tenantId)` | `GET /api/github/orgs/{org}/dashboard?state=all&limit=100` | Bot-authored GitHub issue, PR, review, check, and closure data |
| Analytics tab loads | `fetchUserActivity(org, user, days)` | `GET /api/github/orgs/{org}/user-activity?user={login}&days=21` | GitHub search counts grouped by day for issues, commits, and pull requests |
| Tenant selector | local React state | Uses orgs from `/api/auth/me` | Real |
| Role switch Admin/User | local React state | No backend call | Placeholder RBAC |
| Resolution tab | React state driven by graph stream events | `/api/graph/*` | Dynamic lifecycle UI from graph node events |
| Incidents tab | local React render | Data from dashboard payload | GitHub-backed after dashboard load |
| Pull Requests tab | local React render | Data from dashboard payload | GitHub-backed after dashboard load |
| Analytics tab | local React render | Data from dashboard payload plus user activity endpoint | GitHub-backed visual summaries |
| Architecture tab | local React render | Local PNG asset | Static |

## Placeholder Areas

- RBAC is a frontend role toggle only. It is not enforced by backend yet.
- Resolution Console polls unresolved graph incidents and uses server-sent graph events for selected incident progress. The current backend emits dummy LangGraph-shaped data; replace `backend/app/graph_service.py` with the real LangGraph/sub-agent runner when available.
- The visible incident view is limited to GitHub-backed steps: Issue, Linked PR, Review, Checks, and Merge / Closure.
- The backend dashboard is scoped to the configured automation bot. It searches both `author:airp-automation-bot` and `author:app/airp-automation-bot` so GitHub App bot authors are included.
- Admin view shows all bot-related rows for the selected tenant. User view shows only rows where the logged-in GitHub user is an assignee, requested reviewer, or review author.
- Telemetry, RCA, recovery validation, and documentation stages are not shown until real integrations exist.
- Backend read names are kept internal and are not shown in the dashboard.
- Agent-created PR identification currently depends on linked PRs, labels, and GitHub issue references.
- Commit counts in Analytics depend on GitHub commit search access. If the GitHub App does not have repository contents/metadata access for the relevant repos, GitHub can return partial or zero commit activity.

## Backend

See [backend/README.md](backend/README.md) for complete backend setup and API details.

Quick start:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Docker

Build the full app image from the repository root:

```powershell
docker build -t autonomous-incident-resolution-platform .
```

Run it on port `8000`:

```powershell
docker run --rm -p 8000:8000 --env-file backend/.env autonomous-incident-resolution-platform
```

Open:

```text
http://127.0.0.1:8000
```

The image builds the React frontend, copies it into the Python runtime image, and serves both the UI and `/api/*` routes from FastAPI. For Docker OAuth testing, set these values in `backend/.env` and in the GitHub App/OAuth callback settings:

```env
FRONTEND_URL=http://127.0.0.1:8000
GITHUB_OAUTH_REDIRECT_URI=http://127.0.0.1:8000/api/auth/github/callback
```

## GitHub OAuth Setup

For the old OAuth App flow, create a GitHub OAuth App with callback:

```text
http://127.0.0.1:8000/api/auth/github/callback
```

Set in `backend/.env`:

```env
GITHUB_OAUTH_CLIENT_ID=...
GITHUB_OAUTH_CLIENT_SECRET=...
GITHUB_OAUTH_REDIRECT_URI=http://127.0.0.1:8000/api/auth/github/callback
GITHUB_OAUTH_SCOPES=read:user,user:email,read:org,repo
GITHUB_AUTOMATION_BOT_LOGIN=airp-automation-bot
FRONTEND_URL=http://127.0.0.1:5173
SESSION_SECRET=replace_with_a_long_random_secret
```

For the GitHub App flow with OAuth enabled:

- Use the GitHub App client id and client secret in the same env variables.
- Add `http://127.0.0.1:8000/api/auth/github/callback` as a callback URL in the GitHub App settings.
- Install the GitHub App on the organization/repositories you want to show.
- Authorize the app as the signed-in user.
- GitHub App user access tokens normally return an empty OAuth scope string; this is expected. The backend discovers tenants from `/user/installations` in that mode.

If organizations are not shown as tenants, open:

```text
http://127.0.0.1:8000/api/auth/org-debug
```

Look for `sessionScope`, `user_orgs.count`, `user_memberships.count`, and `user_installations.count`.

## Verification

Frontend:

```bash
npm run build
```

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m compileall app
.\.venv\Scripts\python.exe -c "from app.main import app; print(app.title)"
```

Health:

```text
http://127.0.0.1:8000/api/health
```

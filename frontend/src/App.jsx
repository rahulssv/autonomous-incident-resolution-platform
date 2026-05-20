import { useEffect, useMemo, useRef, useState } from "react";
import architectureDiagram from "../diagram-export-15-5-2026-3_26_43-pm.png";
import {
  authSessionToDashboard,
  beginGitHubLogin,
  buildIncidentResolutionStreamUrl,
  fetchDashboardData,
  fetchAuthSession,
  fetchResolutionIncident,
  fetchResolutionIncidents,
  fetchResolutionStages,
  fetchUserActivity,
  logout as logoutSession,
  mergeDashboardData,
  mockDashboardData
} from "./api.js";
import {
  stages,
} from "./mockGithubData.js";

const roleTabs = ["Admin", "User"];

const resolutionStages = [
  { id: "monitoring", label: "Monitoring", agent: "Monitoring Agent" },
  { id: "correlation", label: "Correlation", agent: "Correlation Agent" },
  { id: "rca", label: "RCA", agent: "RCA Agent" },
  { id: "remediation", label: "Remediation", agent: "Remediation Agent" },
  { id: "documentation", label: "Documentation", agent: "Documentation Agent" },
  { id: "embedding", label: "Knowledge Capture", agent: "Documentation Memory" }
];

const resolutionScenarios = {
  crashloop: {
    signal: "CrashLoopBackOff",
    route: "aks.kubeevents.raw",
    confidence: "High confidence",
    source: "KubeEvents reported BackOff and repeated container restarts.",
    service: "payment service",
    hypothesis: "A deployment change introduced an invalid startup configuration, causing repeated container restarts."
  },
  oom: {
    signal: "OOMKilled",
    route: "aks.kubeevents.raw",
    confidence: "High confidence",
    source: "KubeEvents reported container termination due to memory pressure.",
    service: "checkout worker",
    hypothesis: "The workload memory limit is below the current runtime demand after recent traffic growth."
  },
  latency: {
    signal: "Latency spike",
    route: "aks.containerlogs.raw",
    confidence: "Medium confidence",
    source: "Application logs reported timeout errors above the service SLO.",
    service: "orders API",
    hypothesis: "Downstream dependency saturation is causing request queues and elevated response time."
  }
};

function Pill({ children, tone = "neutral" }) {
  return <span className={`pill ${tone}`}>{children}</span>;
}

function githubItemUrl(incident, type) {
  const number = type === "issue" ? incident.issue : incident.pr;
  const directUrl = type === "issue" ? incident.issueUrl : incident.prUrl;
  if (directUrl) return directUrl;
  if (!number || !incident.repo) return "";
  return `https://github.com/${incident.repo}/${type === "issue" ? "issues" : "pull"}/${number}`;
}

function GitHubNumberLink({ incident, type, prefix, fallback = "None" }) {
  const number = type === "issue" ? incident.issue : incident.pr;
  if (!number) return <span>{fallback}</span>;

  const labelPrefix = prefix ?? (type === "issue" ? "Issue " : "PR ");
  const label = `${labelPrefix}#${number}`;
  const url = githubItemUrl(incident, type);

  if (!url) return <span>{label}</span>;

  return (
    <a
      className="github-number-link"
      href={url}
      target="_blank"
      rel="noreferrer"
      onClick={(event) => event.stopPropagation()}
    >
      {label}
    </a>
  );
}

function onCardKeyDown(event, onClick) {
  if (event.target.closest("a")) return;
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    onClick();
  }
}

function labelTone(label) {
  const normalized = label.toLowerCase();
  if (normalized.includes("sev-0") || normalized.includes("sev-1") || normalized.includes("critical")) {
    return "danger";
  }
  if (normalized.includes("sev-2") || normalized.includes("high") || normalized.includes("approval")) {
    return "amber";
  }
  if (normalized.includes("merged") || normalized.includes("recovery")) {
    return "green";
  }
  if (normalized.includes("agent") || normalized.includes("ai")) {
    return "blue";
  }
  return "neutral";
}

function LabelSummary({ labels = [], max = 2 }) {
  const cleanLabels = labels
    .map((label) => (typeof label === "string" ? label : label?.name))
    .filter(Boolean);
  const visibleLabels = cleanLabels.slice(0, max);
  const hiddenLabels = cleanLabels.slice(max);

  if (!cleanLabels.length) {
    return (
      <span className="label-summary">
        <Pill>No labels</Pill>
      </span>
    );
  }

  return (
    <span className="label-summary">
      {visibleLabels.map((label) => (
        <Pill key={label} tone={labelTone(label)}>
          {label}
        </Pill>
      ))}
      {hiddenLabels.length > 0 && (
        <span
          className="label-more"
          title={hiddenLabels.join(", ")}
          data-tooltip={hiddenLabels.join(", ")}
        >
          +{hiddenLabels.length}
        </span>
      )}
    </span>
  );
}

function statusTone(status = "", health = "") {
  const normalized = status.toLowerCase();
  if (
    normalized.includes("failing") ||
    normalized.includes("changes requested") ||
    normalized.includes("closed")
  ) {
    return "danger";
  }
  if (normalized.includes("review requested") || normalized.includes("draft")) {
    return "amber";
  }
  if (normalized.includes("merged") || normalized.includes("approved")) {
    return "green";
  }
  if (normalized.includes("open") || health === "active") {
    return "blue";
  }
  return "neutral";
}

function loginMatches(value, handle) {
  if (!value || !handle) return false;
  const login = typeof value === "string" ? value : value.login || value.name || value.slug;
  return login?.toLowerCase() === handle.toLowerCase();
}

function listHasLogin(values = [], handle) {
  return values.some((value) => loginMatches(value, handle));
}

function incidentVisibleToUser(incident, handle) {
  return (
    loginMatches(incident.assignee, handle) ||
    listHasLogin(incident.assignees, handle) ||
    listHasLogin(incident.reviewers, handle) ||
    listHasLogin(incident.reviewedBy, handle)
  );
}

function GitHubMark() {
  return (
    <span className="github-mark" aria-hidden="true">
      GH
    </span>
  );
}

function RefreshIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 12a9 9 0 0 1-15.4 6.4" />
      <path d="M3 12a9 9 0 0 1 15.4-6.4" />
      <path d="M18 2v4h-4" />
      <path d="M6 22v-4h4" />
    </svg>
  );
}

function SignOutIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="M16 17l5-5-5-5" />
      <path d="M21 12H9" />
    </svg>
  );
}

function SignIn({ authReady, oauthConfigured, authError, onSignIn }) {
  return (
    <main className="signin-shell">
      <section className="signin-copy">
        <p className="eyebrow">Agentic AI driven operational reliability</p>
        <h1>Autonomous Incident Resolution Platform</h1>
        <p>
          A role-aware command center for GitHub issues, remediation pull
          requests, reviews, checks, and tenant-level incident audit.
        </p>
        <div className="signin-highlights">
          <span>GitHub SSO</span>
          <span>RBAC scoped views</span>
          <span>GitHub API backend</span>
        </div>
      </section>
      <section className="signin-panel" aria-label="Sign in">
        <div className="signin-card-header">
          <GitHubMark />
          <div>
            <strong>GitHub organization</strong>
            <span>Tenant resolved after sign-in</span>
          </div>
        </div>
        <button
          className="primary-action wide"
          onClick={onSignIn}
          disabled={!authReady || !oauthConfigured}
        >
          <GitHubMark />
          {authReady ? "Continue with GitHub" : "Checking session..."}
        </button>
        {authError && <p className="auth-error">{authError}</p>}
        <p className="hint">
          GitHub OAuth returns to the Python backend, which stores a local
          session cookie and uses the user token for GitHub API dashboard reads.
        </p>
      </section>
    </main>
  );
}

function App() {
  const [signedIn, setSignedIn] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [oauthConfigured, setOauthConfigured] = useState(true);
  const [authError, setAuthError] = useState("");
  const [role, setRole] = useState("User");
  const [roleAccessError, setRoleAccessError] = useState("");
  const [dashboardData, setDashboardData] = useState(mockDashboardData);
  const [activityData, setActivityData] = useState(null);
  const [activityError, setActivityError] = useState("");
  const [dataStatus, setDataStatus] = useState("mock");
  const [dataError, setDataError] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [selectedIncidentId, setSelectedIncidentId] = useState("INC-4821");
  const [view, setView] = useState("resolution");

  const sessionUser = dashboardData.sessionUser;
  const tenants = dashboardData.tenants;
  const incidents = dashboardData.incidents;
  const auditEvents = dashboardData.auditEvents;
  const tenant = tenants.find((item) => item.id === tenantId) || tenants[0] || null;
  // RBAC: a user is only an admin if their real GitHub org membership role for
  // the *currently selected* tenant is "admin". This is derived from
  // membershipRole returned by /user/memberships/orgs in the auth payload.
  const isAdminOfCurrentTenant = Boolean(tenant?.isAdmin);

  useEffect(() => {
    // If the selected tenant changes and the user isn't admin there,
    // force the role back to "User" so they cannot see admin views.
    if (!isAdminOfCurrentTenant && role === "Admin") {
      setRole("User");
    }
  }, [isAdminOfCurrentTenant, role]);

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams(window.location.search);
    const oauthMessage = params.get("message");
    if (oauthMessage) {
      setAuthError(oauthMessage);
      window.history.replaceState({}, "", window.location.pathname);
    }

    fetchAuthSession()
      .then((authSession) => {
        if (cancelled) return;
        setOauthConfigured(authSession.oauthConfigured !== false);
        if (authSession.authenticated) {
          const nextDashboard = authSessionToDashboard(authSession, mockDashboardData);
          setDashboardData(nextDashboard);
          setSignedIn(true);
          const firstTenant = nextDashboard.tenants[0];
          if (firstTenant) {
            setTenantId(firstTenant.id);
          } else {
            setTenantId("");
            setDataStatus("live");
            setDataError(
              "No GitHub organization tenants were returned. Confirm the GitHub App is installed on the organization and that this user has authorized the app."
            );
          }
        } else if (authSession.oauthConfigured === false) {
          setAuthError("GitHub OAuth is not configured in the backend .env file.");
        }
      })
      .catch((error) => {
        if (cancelled) return;
        setOauthConfigured(false);
        setAuthError("Unable to reach the backend auth service.");
        console.warn(error);
      })
      .finally(() => {
        if (!cancelled) {
          setAuthReady(true);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!authReady || !signedIn || !tenant?.githubOrg) return;

    let cancelled = false;
    setDataStatus("loading");
    setDataError("");

    fetchDashboardData(tenant.githubOrg, tenant.id)
      .then((payload) => {
        if (cancelled) return;
        setDashboardData((current) => mergeDashboardData(current, payload, tenant.id));
        setDataStatus("live");
        const firstIncident = payload.incidents[0];
        if (firstIncident) {
          setSelectedIncidentId(firstIncident.id);
        }
      })
      .catch((error) => {
        if (cancelled) return;
        setDataStatus("live");
        setDataError(
          "Unable to load GitHub organization dashboard data. Check backend logs or org OAuth access."
        );
        console.warn(error);
      });

    return () => {
      cancelled = true;
    };
  }, [authReady, signedIn, tenantId]);

  useEffect(() => {
    if (!authReady || !signedIn || !tenant?.githubOrg || !sessionUser.handle) return;

    let cancelled = false;
    setActivityData(null);
    setActivityError("");

    fetchUserActivity(tenant.githubOrg, sessionUser.handle, 21)
      .then((payload) => {
        if (cancelled) return;
        setActivityData(payload);
      })
      .catch((error) => {
        if (cancelled) return;
        setActivityData(null);
        setActivityError(
          "Unable to load GitHub user activity. Check GitHub App permissions for issues, pull requests, and commit search."
        );
        console.warn(error);
      });

    return () => {
      cancelled = true;
    };
  }, [authReady, signedIn, tenantId, sessionUser.handle]);

  const tenantIncidents = useMemo(
    () =>
      tenant
        ? incidents.filter((incident) => incident.tenantId === tenant.id)
        : [],
    [incidents, tenant]
  );

  function refreshUserActivityData() {
    if (!tenant?.githubOrg || !sessionUser.handle) return Promise.resolve();

    setActivityError("");
    return fetchUserActivity(tenant.githubOrg, sessionUser.handle, 21)
      .then((payload) => {
        setActivityData(payload);
      })
      .catch((error) => {
        setActivityData(null);
        setActivityError(
          "Unable to refresh GitHub user activity. Check GitHub App permissions for issues, pull requests, and commit search."
        );
        console.warn(error);
      });
  }

  function refreshDashboardData() {
    if (!tenant?.githubOrg) return;

    setDataStatus("loading");
    setDataError("");
    refreshUserActivityData();

    fetchDashboardData(tenant.githubOrg, tenant.id)
      .then((payload) => {
        setDashboardData((current) => mergeDashboardData(current, payload, tenant.id));
        setDataStatus("live");
        if (!payload.incidents.some((incident) => incident.id === selectedIncidentId)) {
          setSelectedIncidentId(payload.incidents[0]?.id || "");
        }
      })
      .catch((error) => {
        setDataStatus("live");
        setDataError(
          "Unable to refresh GitHub dashboard data. Check backend logs or GitHub access."
        );
        console.warn(error);
      });
  }

  const visibleIncidents =
    role === "Admin"
      ? tenantIncidents
      : tenantIncidents.filter((incident) =>
          incidentVisibleToUser(incident, sessionUser.handle)
        );

  const selectedIncident =
    visibleIncidents.find((incident) => incident.id === selectedIncidentId) ||
    visibleIncidents[0] ||
    null;

  if (!authReady || !signedIn) {
    return (
      <SignIn
        authReady={authReady}
        oauthConfigured={oauthConfigured}
        authError={authError}
        onSignIn={beginGitHubLogin}
      />
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark">AI</div>
          <div>
            <strong>Autonomous Incident Resolution Platform</strong>
            <span>Incident operations</span>
          </div>
        </div>

        <nav className="nav-stack" aria-label="Primary">
          <button
            className={view === "resolution" ? "active" : ""}
            onClick={() => setView("resolution")}
            title="Resolution"
          >
            Resolution
          </button>
          <button
            className={view === "workflow" ? "active" : ""}
            onClick={() => setView("workflow")}
            title="Incidents"
          >
            Incidents
          </button>
          <button
            className={view === "prs" ? "active" : ""}
            onClick={() => setView("prs")}
            title="Pull requests"
          >
            Pull Requests
          </button>
          <button
            className={view === "analytics" ? "active" : ""}
            onClick={() => setView("analytics")}
            title="Analytics"
          >
            Analytics
          </button>
          <button
            className={view === "architecture" ? "active" : ""}
            onClick={() => setView("architecture")}
            title="Architecture"
          >
            Architecture
          </button>
        </nav>

        <div className="tenant-block">
          <label htmlFor="tenant">Tenant</label>
          {tenants.length ? (
            <>
              <select
                id="tenant"
                value={tenant?.id || ""}
                onChange={(event) => {
                  setTenantId(event.target.value);
                  const next = incidents.find(
                    (incident) => incident.tenantId === event.target.value
                  );
                  setSelectedIncidentId(next?.id || "");
                }}
                disabled={role !== "Admin"}
              >
                {tenants.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
              <span>{tenant?.githubOrg}</span>
            </>
          ) : (
            <span>No GitHub orgs found</span>
          )}
        </div>
      </aside>

      <main className="dashboard">
        <header className="topbar">
          <div>
            <h1>
              {view === "analytics"
                ? "User Activity Analytics"
                : view === "architecture"
                  ? "Architecture Reference"
                : view === "prs"
                  ? role === "Admin"
                    ? "Bot-Created Pull Requests"
                    : "My Pull Request Reviews"
                : view === "resolution"
                  ? "Resolution Console"
                  : role === "Admin"
                      ? "Incidents"
                      : "My Assigned Incidents"}
            </h1>
            {dataError && <p className="data-warning">{dataError}</p>}
          </div>
          <div className="topbar-actions">
            <div className="role-control">
              <div className="role-switch" aria-label="Role selector">
                {roleTabs.map((item) => {
                  const isAdminButton = item === "Admin";
                  const lockedOut = isAdminButton && !isAdminOfCurrentTenant;
                  return (
                    <button
                      key={item}
                      className={`${role === item ? "active" : ""}${lockedOut ? " role-locked" : ""}`}
                      title={
                        lockedOut
                          ? "Not authorized. Admin requires admin membership on this GitHub org."
                          : undefined
                      }
                      aria-disabled={lockedOut ? "true" : undefined}
                      onClick={() => {
                        if (lockedOut) {
                          setRoleAccessError(
                            `Not authorized: you do not have admin role on "${tenant?.name || tenant?.githubOrg || "this org"}". Admin view requires GitHub org admin membership.`
                          );
                          window.setTimeout(() => setRoleAccessError(""), 5000);
                          return;
                        }
                        setRoleAccessError("");
                        setRole(item);
                        const next =
                          isAdminButton
                            ? tenantIncidents[0]
                            : tenantIncidents.find(
                                (incident) =>
                                  incidentVisibleToUser(incident, sessionUser.handle)
                              );
                        if (next) setSelectedIncidentId(next.id);
                      }}
                    >
                      {lockedOut && <span className="role-lock-icon" aria-hidden="true">🔒</span>}
                      {item}
                    </button>
                  );
                })}
              </div>
              {roleAccessError && (
                <p className="role-access-error" role="alert">{roleAccessError}</p>
              )}
            </div>
            <div className="account-cluster">
              <div className="user-chip">
                <span>{sessionUser.name.charAt(0)}</span>
                <div>
                  <strong>{sessionUser.name}</strong>
                  <small>{sessionUser.handle}</small>
                </div>
              </div>
              <button
                className="signout-action"
                title="Sign out"
                aria-label="Sign out"
                onClick={() => {
                  logoutSession().finally(() => {
                    setSignedIn(false);
                    setDashboardData(mockDashboardData);
                    setActivityData(null);
                    setActivityError("");
                    setTenantId("");
                  });
                }}
              >
                <SignOutIcon />
              </button>
            </div>
          </div>
        </header>

        {!tenant && (
          <NoTenantView />
        )}

        {tenant && view === "resolution" && (
          <ResolutionConsoleView />
        )}

        {tenant && view === "workflow" && role === "Admin" && (
          <AdminWorkflow
            tenant={tenant}
            incidents={visibleIncidents}
            selectedIncident={selectedIncident}
            onSelect={setSelectedIncidentId}
            onRefresh={refreshDashboardData}
          />
        )}

        {tenant && view === "workflow" && role === "User" && (
          <UserWorkflow
            incidents={visibleIncidents}
            selectedIncident={selectedIncident}
            onSelect={setSelectedIncidentId}
            onRefresh={refreshDashboardData}
          />
        )}

        {tenant && view === "prs" && (
          <PullRequestView
            role={role}
            incidents={visibleIncidents}
            selectedIncident={selectedIncident}
            onSelect={setSelectedIncidentId}
            onRefresh={refreshDashboardData}
          />
        )}

        {tenant && view === "analytics" && (
          <AnalyticsView
            role={role}
            incidents={visibleIncidents}
            onRefresh={refreshDashboardData}
            activityData={activityData}
            activityError={activityError}
            activityUser={sessionUser.handle}
          />
        )}

        {tenant && view === "architecture" && <ArchitectureView onRefresh={refreshDashboardData} />}
      </main>
    </div>
  );
}

function ResolutionConsoleView() {
  const streamRef = useRef(null);
  const stageItemsRef = useRef(resolutionStages);
  const selectedIdRef = useRef("");
  const autoRunSeenRef = useRef(new Set());
  const isRunningRef = useRef(false);
  const [stageItems, setStageItems] = useState(resolutionStages);
  const [queue, setQueue] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [pollStatus, setPollStatus] = useState("Polling unresolved incidents");
  const [detailLoading, setDetailLoading] = useState(false);
  const [graphError, setGraphError] = useState("");
  const [runState, setRunState] = useState("Select Incident");
  const [runStatus, setRunStatus] = useState("");
  const [incident, setIncident] = useState(null);
  const [activeStageId, setActiveStageId] = useState("");
  const [activeStageTitle, setActiveStageTitle] = useState("No active phase");
  const [stageSummary, setStageSummary] = useState(
    "Resolution details will appear here after an error is detected."
  );
  const [completedStages, setCompletedStages] = useState([]);
  const [metrics, setMetrics] = useState({ events: 0, tools: 0, models: 0 });
  const [rcaHypothesis, setRcaHypothesis] = useState(
    "RCA output will appear after runtime evidence is collected."
  );
  const [evidenceRefs, setEvidenceRefs] = useState([]);
  const [documentationDraft, setDocumentationDraft] = useState([]);

  const isRunning = runStatus === "running";

  useEffect(() => {
    stageItemsRef.current = stageItems;
  }, [stageItems]);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    isRunningRef.current = runStatus === "running";
  }, [runStatus]);

  useEffect(() => {
    let cancelled = false;
    fetchResolutionStages()
      .then((payload) => {
        if (cancelled || !payload?.items?.length) return;
        setStageItems(payload.items);
        stageItemsRef.current = payload.items;
      })
      .catch((error) => {
        console.warn(error);
      });

    return () => {
      cancelled = true;
      closeResolutionStream(streamRef);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    function poll() {
      loadResolutionQueue({ cancelled });
    }

    poll();
    const interval = window.setInterval(poll, 3000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!selectedId) {
      resetResolutionDetail();
      return;
    }

    closeResolutionStream(streamRef);
    setDetailLoading(true);
    setGraphError("");
    fetchResolutionIncident(selectedId)
      .then((payload) => {
        applyResolutionDetail(payload);
      })
      .catch((error) => {
        setGraphError("Unable to load LangGraph incident details.");
        console.warn(error);
      })
      .finally(() => {
        setDetailLoading(false);
      });
  }, [selectedId]);

  function loadResolutionQueue({ cancelled = false } = {}) {
    setPollStatus("Polling unresolved incidents");
    fetchResolutionIncidents()
      .then((payload) => {
        if (cancelled) return;
        const items = payload.items || [];
        setQueue(items);
        setGraphError("");
        setPollStatus(`Polling active - ${items.length} unresolved`);
        if (!selectedIdRef.current || !items.some((item) => item.id === selectedIdRef.current)) {
          setSelectedId(items[0]?.id || "");
        }

        // Auto-run: find newest real (UUID) unresolved incident we haven't streamed yet.
        // Real incidents have a "-" in their id (uuid); demo ones look like "LG-1001".
        const candidate = items.find(
          (item) =>
            typeof item.id === "string"
            && item.id.length > 20
            && item.id.includes("-")
            && item.state !== "resolved"
            && !autoRunSeenRef.current.has(item.id)
        );
        if (candidate && !isRunningRef.current) {
          autoRunSeenRef.current.add(candidate.id);
          setSelectedId(candidate.id);
          // Small delay so the detail fetch can populate state first; the stream
          // doesn't depend on it but it makes the UI render the selected row.
          window.setTimeout(() => startSelectedResolution(candidate.id), 50);
        }
      })
      .catch((error) => {
        if (cancelled) return;
        setPollStatus("Polling failed");
        setGraphError("Unable to poll unresolved LangGraph incidents.");
        console.warn(error);
      });
  }

  function resetResolutionDetail() {
    setIncident(null);
    setRunState("No Incident");
    setRunStatus("");
    setActiveStageId("");
    setActiveStageTitle("No active phase");
    setStageSummary("Select an unresolved incident to inspect its LangGraph node progress.");
    setCompletedStages([]);
    setMetrics({ events: 0, tools: 0, models: 0 });
    setRcaHypothesis("RCA output will appear after runtime evidence is collected.");
    setEvidenceRefs([]);
    setDocumentationDraft([]);
  }

  function applyResolutionDetail(payload) {
    if (payload.stages?.length) {
      setStageItems(payload.stages);
      stageItemsRef.current = payload.stages;
    }

    const nextIncident = payload.incident;
    if (nextIncident) {
      setIncident({
        id: nextIncident.id || nextIncident.incident_id,
        title: nextIncident.title,
        severity: nextIncident.severity,
        status: nextIncident.status,
        signal: nextIncident.signal,
        route: nextIncident.route,
        confidence: nextIncident.confidence,
        service: nextIncident.service,
        description: nextIncident.description,
        issueCreated: nextIncident.issueCreated
      });
      setRunState(nextIncident.issueCreated ? "Issue Created" : nextIncident.status || "Unresolved");
      setRunStatus(nextIncident.issueCreated ? "done" : "");
    }

    setActiveStageId(payload.currentStage || "");
    setActiveStageTitle(payload.currentStageLabel || stageLabelFor(payload.currentStage, stageItemsRef.current));
    setStageSummary(payload.summary || "LangGraph node details will appear here.");
    setCompletedStages(payload.completedStages || []);
    updateResolutionMetrics(payload.snapshot, setMetrics);
    setRcaHypothesis(payload.rca?.hypothesis || "RCA output will appear after runtime evidence is collected.");
    setEvidenceRefs(payload.rca?.evidence || []);
    setDocumentationDraft(documentationRows(payload.documentation));
  }

  function startSelectedResolution(explicitId) {
    const targetId = explicitId || selectedId;
    if (!targetId || isRunningRef.current) return;
    closeResolutionStream(streamRef);

    // Reset stage progression so live transitions are visible.
    setCompletedStages([]);
    setActiveStageId(stageItemsRef.current[0]?.id || "monitoring");
    setActiveStageTitle(stageItemsRef.current[0]?.label || "Monitoring");
    setStageSummary("Workflow started — waiting for first agent.");

    setRunState("Resolving");
    setRunStatus("running");
    isRunningRef.current = true;

    const stream = new EventSource(buildIncidentResolutionStreamUrl(targetId), {
      withCredentials: true
    });
    streamRef.current = stream;

    stream.addEventListener("metadata", (event) => {
      const data = parseStreamEvent(event);
      if (data.detail) {
        applyResolutionDetail(data.detail);
        setRunStatus("running");
      }
      if (data.incident) {
        setIncident((current) => ({
          ...(current || {}),
          id: data.incident.id || data.incident.incident_id || selectedId,
          title: data.incident.title || current?.title,
          severity: data.incident.severity || current?.severity,
          status: data.incident.status || current?.status
        }));
      }
    });

    stream.addEventListener("run_started", (event) => {
      const data = parseStreamEvent(event);
      setRunState("Resolving");
      setRunStatus("running");
      setActiveStageId(data.currentStage || stageItemsRef.current[0]?.id || "");
      setActiveStageTitle(stageLabelFor(data.currentStage, stageItemsRef.current));
      setStageSummary(data.summary || "Incident resolution started.");
      updateResolutionMetrics(data.snapshot, setMetrics);
    });

    stream.addEventListener("stage_completed", (event) => {
      const data = parseStreamEvent(event);
      const stage = stageItemsRef.current.find((item) => item.id === data.stage);
      // Add ONLY this stage to completedStages — animates one-at-a-time.
      // Don't blat with data.detail.completedStages (it may already contain all stages
      // for live polling against an already-progressing workflow).
      setCompletedStages((current) => [...new Set([...current, data.stage])]);
      setActiveStageId(data.nextStage || "");
      setActiveStageTitle(stage?.label || data.stage || "Stage");
      const dur = data.duration_ms != null ? ` (${(data.duration_ms / 1000).toFixed(2)}s)` : "";
      setStageSummary(`${stage?.label || data.stage} completed${dur}.`);
      updateResolutionMetrics(data.snapshot, setMetrics);
      setIncident((current) =>
        current ? { ...current, status: data.nextStage ? "Resolving" : "Resolved" } : current
      );
      // Pull RCA hypothesis / evidence / documentation from data.detail without
      // overriding completedStages / activeStageId.
      if (data.detail) {
        const d = data.detail;
        if (d.rca?.hypothesis) setRcaHypothesis(d.rca.hypothesis);
        if (d.rca?.evidence) setEvidenceRefs(d.rca.evidence);
        if (d.documentation) setDocumentationDraft(documentationRows(d.documentation));
      }
      updateResolutionArtifacts(data, setRcaHypothesis, setEvidenceRefs, setDocumentationDraft);
      setRunStatus("running");
    });

    stream.addEventListener("run_completed", (event) => {
      const data = parseStreamEvent(event);
      updateResolutionMetrics(data.snapshot, setMetrics);
      setRunState(data.issueCreated ? "Issue Created" : "Resolved");
      setRunStatus("done");
      isRunningRef.current = false;
      setActiveStageId("");
      setIncident((current) =>
        current
          ? { ...current, status: "Issue created", issueCreated: data.issueCreated }
          : current
      );
      if (data.detail) {
        applyResolutionDetail(data.detail);
      }
      closeResolutionStream(streamRef);
    });

    stream.addEventListener("resolution_error", (event) => {
      const data = parseStreamEvent(event);
      setRunState("Error");
      setRunStatus("error");
      isRunningRef.current = false;
      closeResolutionStream(streamRef);
    });

    stream.onerror = () => {
      setRunState("Interrupted");
      setRunStatus("error");
      closeResolutionStream(streamRef);
    };
  }

  return (
    <div className="resolution-page">
      <section className="resolution-header">
        <div>
          <p className="resolution-eyebrow">Incident operations</p>
          <h2>Autonomous Incident Resolution</h2>
          <p>
            Poll unresolved LangGraph incidents, inspect each node state, and run the
            selected incident through the resolution pipeline.
          </p>
        </div>
        <div className={`resolution-run-state ${runStatus}`}>{runState}</div>
      </section>

      <section className="resolution-workspace">
        <aside className="resolution-queue-panel" aria-label="Unresolved incidents">
          <div className="resolution-panel-heading">
            <p className="resolution-eyebrow">LangGraph queue</p>
            <h3>Unresolved Incidents</h3>
            <span>{pollStatus}</span>
          </div>
          {graphError && <p className="data-warning">{graphError}</p>}
          <div className="resolution-queue-list">
            {queue.length ? (
              queue.map((item) => (
                <button
                  key={item.id}
                  className={`resolution-queue-card ${selectedId === item.id ? "active" : ""}`}
                  onClick={() => setSelectedId(item.id)}
                >
                  <div>
                    <strong>{item.title}</strong>
                    <span>{item.signal} - {item.currentStageLabel}</span>
                  </div>
                  <div className="resolution-queue-meta">
                    <span>{item.id}</span>
                    <span>{item.severity}</span>
                    <span>{item.completedCount}/{item.totalStages}</span>
                  </div>
                </button>
              ))
            ) : (
              <EmptyState title="No unresolved incidents" detail="Polling will add LangGraph incidents here." />
            )}
          </div>
        </aside>

        <section className="resolution-detail-panel">
          {!incident && !detailLoading && (
            <EmptyState title="Select an incident" detail="LangGraph node progress will appear here." />
          )}
          {detailLoading && (
            <EmptyState title="Loading incident" detail="Fetching LangGraph detail for the selected incident." />
          )}
          {incident && (
            <>
              <section className="resolution-stage-panel" aria-label="Incident resolution lifecycle">
                <div className="resolution-panel-heading">
                  <p className="resolution-eyebrow">Resolution pipeline</p>
                  <h3>{incident.title}</h3>
                </div>
                <ol className="resolution-stage-list">
                  {stageItems.map((stage, index) => (
                    <li
                      key={stage.id}
                      className={`resolution-stage-item ${
                        activeStageId === stage.id ? "current" : ""
                      } ${completedStages.includes(stage.id) ? "complete" : ""}`}
                    >
                      <span className="resolution-stage-dot">{index + 1}</span>
                      <span>
                        <span className="resolution-stage-name">{stage.label}</span>
                        <span className="resolution-stage-agent">{stage.agent}</span>
                      </span>
                    </li>
                  ))}
                </ol>
              </section>

              <section className="resolution-workbench">
                <div className="resolution-detection-card">
                  <div>
                    <p className="resolution-eyebrow">Detection</p>
                    <h3>{incident.signal || "Detected signal"}</h3>
                    <p>{incident.description || "LangGraph incident context will appear here."}</p>
                  </div>
                  <div className="resolution-signal-facts">
                    <span>{incident.signal || "No signal"}</span>
                    <span>{incident.route || "-"}</span>
                    <span>{incident.confidence || "-"}</span>
                  </div>
                </div>

                <div className="resolution-incident-card">
                  <div>
                    <p className="resolution-eyebrow">Incident</p>
                    <h3>{incident.title}</h3>
                  </div>
                  <div className="resolution-incident-meta">
                    <span>{incident.id}</span>
                    <span>{incident.severity}</span>
                    <span>{incident.status}</span>
                  </div>
                </div>

                {incident.issueCreated && (
                  <div className="resolution-issue-note">
                    GitHub issue #{incident.issueCreated.number} was created in {incident.issueCreated.repo}.
                    Refresh the Incidents tab to see it after GitHub returns it.
                  </div>
                )}

                <div className="resolution-agent-grid">
                  <article className="resolution-agent-output">
                    <div className="resolution-panel-heading">
                      <p className="resolution-eyebrow">Current Phase</p>
                      <h3>{activeStageTitle}</h3>
                    </div>
                    <p className="resolution-summary">{stageSummary}</p>
                    <dl className="resolution-metrics">
                      <div>
                        <dt>Evidence</dt>
                        <dd>{metrics.tools}</dd>
                      </div>
                      <div>
                        <dt>AI Calls</dt>
                        <dd>{metrics.models}</dd>
                      </div>
                    </dl>
                  </article>

                  <article className="resolution-agent-output">
                    <div className="resolution-panel-heading">
                      <p className="resolution-eyebrow">RCA</p>
                      <h3>Hypothesis</h3>
                    </div>
                    <p className="resolution-summary">{rcaHypothesis}</p>
                    <div className="resolution-chip-row">
                      {evidenceRefs.map((ref) => (
                        <span key={ref}>{ref}</span>
                      ))}
                    </div>
                  </article>

                  <article className="resolution-agent-output wide">
                    <div className="resolution-panel-heading">
                      <p className="resolution-eyebrow">Documentation</p>
                      <h3>Resolution Record</h3>
                    </div>
                    <div className="resolution-doc-preview">
                      {documentationDraft.length ? (
                        documentationDraft.map(([label, value]) => (
                          <p key={label}>
                            <strong>{label}:</strong> {value}
                          </p>
                        ))
                      ) : (
                        <p>No resolution record yet.</p>
                      )}
                    </div>
                  </article>
                </div>
              </section>
            </>
          )}
        </section>
      </section>
    </div>
  );
}

function stageLabelFor(stageId, stageItems = resolutionStages) {
  return stageItems.find((stage) => stage.id === stageId)?.label || stageId || "No active phase";
}

function documentationRows(report) {
  if (!report) return [];
  return [
    ["Executive", report.executive_summary || "-"],
    ["Root Cause", report.root_cause_summary || "-"],
    ["Remediation", report.remediation_summary || "-"]
  ];
}

function closeResolutionStream(streamRef) {
  if (streamRef.current) {
    streamRef.current.close();
    streamRef.current = null;
  }
}

function parseStreamEvent(event) {
  try {
    return JSON.parse(event.data);
  } catch {
    return {};
  }
}

function updateResolutionMetrics(snapshot, setMetrics) {
  if (!snapshot) return;
  setMetrics({
    events: snapshot.agent_event_count ?? 0,
    tools: snapshot.tool_call_count ?? 0,
    models: snapshot.model_call_count ?? 0
  });
}

function updateResolutionArtifacts(
  data,
  setRcaHypothesis,
  setEvidenceRefs,
  setDocumentationDraft
) {
  const hypotheses = data.update?.rca_hypotheses || [];
  const topHypothesis = hypotheses[0];
  if (topHypothesis?.hypothesis) {
    setRcaHypothesis(topHypothesis.hypothesis);
  }

  const refs = data.update?.rca_evidence_bundle?.evidence_sources || [];
  if (refs.length) {
    setEvidenceRefs(refs);
  }

  const report = data.update?.documentation_report;
  if (report) {
    setDocumentationDraft([
      ["Executive", report.executive_summary || "-"],
      ["Root Cause", report.root_cause_summary || "-"],
      ["Remediation", report.remediation_summary || "-"]
    ]);
  }
}

function NoTenantView() {
  return (
    <section className="no-tenant-panel">
      <h2>No GitHub organization tenant found</h2>
      <p>
        The dashboard creates tenants from GitHub organizations or GitHub App
        installations returned for the signed-in account. Make sure the GitHub
        App is installed on the organization and this user has authorized it.
      </p>
    </section>
  );
}

function AdminWorkflow({ tenant, incidents, selectedIncident, onSelect, onRefresh }) {
  const activeCount = incidents.filter((incident) => incident.health === "active").length;
  const prCount = incidents.filter((incident) => incident.pr).length;
  const reviewCount = incidents.filter((incident) => incident.reviewers?.length).length;

  return (
    <div className="content-grid">
      <section className="metrics-row compact-metrics" aria-label="Tenant metrics">
        <MetricCard label="Active incidents" value={activeCount} tone="danger" />
        <MetricCard label="Bot PRs" value={prCount} tone="blue" />
        <MetricCard label="Review requests" value={reviewCount} tone="amber" />
        <MetricCard label="Repositories" value={tenant.repositories} tone="green" />
      </section>

      <section className="split-layout">
        <div className="incident-list" aria-label="Tenant incidents">
          <SectionHeader
            title="Incident Queue"
            subtitle="Admin visibility across airp-automation-bot issues, PRs, reviews, checks, and closure state."
            onRefresh={onRefresh}
          />
          {!incidents.length && (
            <EmptyState title="No bot-created issues or PRs found" detail="No GitHub issues or PRs authored by the configured automation bot were returned." />
          )}
          {!!incidents.length && (
            <div className="incident-scroll">
              {incidents.map((incident) => (
                <IncidentRow
                  key={incident.id}
                  incident={incident}
                  active={incident.id === selectedIncident?.id}
                  onClick={() => onSelect(incident.id)}
                />
              ))}
            </div>
          )}
        </div>

        <div className="incident-detail">
          {selectedIncident ? (
            <>
              <IncidentHeader incident={selectedIncident} />
              <ProcessTimeline incident={selectedIncident} />
            </>
          ) : (
            <EmptyState title="Select an issue" detail="GitHub issue details will appear here." />
          )}
        </div>
      </section>
    </div>
  );
}

function UserWorkflow({ incidents, selectedIncident, onSelect, onRefresh }) {
  const reviewCount = incidents.filter((incident) => incident.reviewers?.length).length;
  const passingChecks = incidents.reduce(
    (total, incident) => total + (incident.checks?.passing || 0),
    0
  );
  const totalChecks = incidents.reduce(
    (total, incident) => total + (incident.checks?.total || 0),
    0
  );
  const failingChecks = incidents.filter((incident) => incident.checks?.failingName).length;

  return (
    <div className="content-grid">
      <section className="metrics-row compact-metrics" aria-label="User metrics">
        <MetricCard label="Incidents to track" value={incidents.length} tone="blue" />
        <MetricCard label="Review requests" value={reviewCount} tone="amber" />
        <MetricCard label="Checks passing" value={`${passingChecks}/${totalChecks}`} tone="green" />
        <MetricCard label="Failing checks" value={failingChecks} tone="neutral" />
      </section>

      <section className="split-layout user-layout">
        <div className="incident-list">
          <SectionHeader
            title="My Assigned Issues & Reviews"
            subtitle="airp-automation-bot issues and PRs where you are assignee or reviewer."
            onRefresh={onRefresh}
          />
          {!incidents.length && (
            <EmptyState title="No assigned or review-requested work" detail="No bot-created GitHub issue or PR has you as assignee or requested reviewer." />
          )}
          {!!incidents.length && (
            <div className="incident-scroll">
              {incidents.map((incident) => (
                <IncidentRow
                  key={incident.id}
                  incident={incident}
                  active={incident.id === selectedIncident?.id}
                  onClick={() => onSelect(incident.id)}
                />
              ))}
            </div>
          )}
        </div>
        <div className="incident-detail">
          {selectedIncident ? (
            <>
              <IncidentHeader incident={selectedIncident} compact />
              <PullRequestTracker incident={selectedIncident} />
            </>
          ) : (
            <EmptyState title="No issue selected" detail="Assigned issue and PR status will appear here." />
          )}
        </div>
      </section>
    </div>
  );
}

function PullRequestView({ role, incidents, selectedIncident, onSelect, onRefresh }) {
  const pullRequests = incidents.filter((incident) => incident.pr);
  const selectedPullRequest =
    pullRequests.find((incident) => incident.id === selectedIncident?.id) || null;
  const reviewCount = pullRequests.filter((incident) => incident.reviewers?.length).length;
  const passingChecks = pullRequests.reduce(
    (total, incident) => total + (incident.checks?.passing || 0),
    0
  );
  const totalChecks = pullRequests.reduce(
    (total, incident) => total + (incident.checks?.total || 0),
    0
  );
  const failingChecks = pullRequests.filter((incident) => incident.checks?.failingName).length;
  const listTitle = role === "Admin" ? "Pull Request Queue" : "My Pull Request Reviews";
  const listSubtitle =
    role === "Admin"
      ? "Bot-created pull requests with review, check, and closure state."
      : "Bot-created pull requests where you are requested as reviewer.";

  return (
    <div className="content-grid">
      <section className="metrics-row compact-metrics" aria-label="Pull request metrics">
        <MetricCard label="Total pull requests" value={pullRequests.length} tone="blue" />
        <MetricCard label="Review requests" value={reviewCount} tone="amber" />
        <MetricCard label="Checks passing" value={`${passingChecks}/${totalChecks}`} tone="green" />
        <MetricCard label="Failing checks" value={failingChecks} tone="neutral" />
      </section>

      <section className="split-layout pr-layout">
        <div className="incident-list pr-list" aria-label="Pull request list">
          <SectionHeader title={listTitle} subtitle={listSubtitle} onRefresh={onRefresh} />
          {!pullRequests.length && (
            <EmptyState title="No bot-created pull requests found" detail="No matching bot-authored PRs are visible for this role." />
          )}
          {!!pullRequests.length && (
            <div className="incident-scroll pr-scroll">
              {pullRequests.map((incident) => (
                <article
                  key={incident.id}
                  className={`pr-card ${selectedPullRequest?.id === incident.id ? "active" : ""}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelect(incident.id)}
                  onKeyDown={(event) => onCardKeyDown(event, () => onSelect(incident.id))}
                >
                  <div className="pr-card-header">
                    <GitHubNumberLink incident={incident} type="pr" />
                    <Pill tone={incident.checks.passing === incident.checks.total ? "green" : "amber"}>
                      {incident.checks.passing}/{incident.checks.total} checks
                    </Pill>
                  </div>
                  <strong>{incident.title}</strong>
                  <small>{incident.repo}</small>
                  <div className="pr-meta-row">
                    <span>{incident.branch}</span>
                    <span>{incident.status}</span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>

        <div className="incident-detail pr-detail">
          {selectedPullRequest ? (
            <PullRequestTracker incident={selectedPullRequest} full onRefresh={onRefresh} />
          ) : (
            <EmptyState title="Select a pull request" detail="Review, checks, labels, and linked incident details will appear here." />
          )}
        </div>
      </section>
    </div>
  );
}

function analyticsForIncidents(incidents) {
  const now = Date.now();
  const timeValues = incidents
    .map((incident) => Date.parse(incident.updatedAt || incident.startedAt))
    .filter(Number.isFinite);
  const ageValues = incidents
    .map((incident) => Date.parse(incident.startedAt))
    .filter(Number.isFinite)
    .map((startedAt) => Math.max(now - startedAt, 0));
  const recent24h = timeValues.filter((value) => now - value <= 24 * 60 * 60 * 1000).length;
  const oldestOpenAge = ageValues.length ? Math.max(...ageValues) : 0;
  const averageAge = ageValues.length
    ? ageValues.reduce((total, value) => total + value, 0) / ageValues.length
    : 0;
  const issueRows = incidents.filter((incident) => incident.sourceType !== "pull_request").length;
  const prOnlyRows = incidents.filter((incident) => incident.sourceType === "pull_request").length;
  const linkedPrs = incidents.filter((incident) => incident.pr).length;
  const reviewRequests = incidents.filter((incident) => incident.reviewers?.length).length;
  const checksPassing = incidents.reduce(
    (total, incident) => total + (incident.checks?.passing || 0),
    0
  );
  const checksTotal = incidents.reduce(
    (total, incident) => total + (incident.checks?.total || 0),
    0
  );
  const failingChecks = incidents.filter((incident) => incident.checks?.failingName).length;
  const draftPrs = incidents.filter((incident) =>
    (incident.status || "").toLowerCase().includes("draft")
  ).length;
  const openPrs = incidents.filter((incident) =>
    (incident.status || "").toLowerCase().includes("open")
  ).length;
  const mergedPrs = incidents.filter((incident) =>
    (incident.status || "").toLowerCase().includes("merged")
  ).length;

  return {
    issueRows,
    prOnlyRows,
    linkedPrs,
    reviewRequests,
    checksPassing,
    checksTotal,
    failingChecks,
    draftPrs,
    openPrs,
    mergedPrs,
    recent24h,
    oldestOpenAge,
    averageAge,
    recentItems: recentItems(incidents)
  };
}

function formatDuration(ms) {
  if (!ms) return "0m";
  const minutes = Math.floor(ms / 60000);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function recentItems(incidents) {
  return [...incidents]
    .sort(
      (left, right) =>
        Date.parse(right.updatedAt || right.startedAt || 0) -
        Date.parse(left.updatedAt || left.startedAt || 0)
    )
    .slice(0, 5);
}

function formatShortDate(value) {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return "Unknown";
  return new Date(parsed).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function RecentActivityList({ items }) {
  return (
    <div className="recent-list">
      {items.map((item) => (
        <article key={item.id} className="recent-item">
          <div>
            <strong>{item.title}</strong>
            <span>{item.repo}</span>
          </div>
          <div>
            <Pill tone={statusTone(item.status, item.health)}>{item.status}</Pill>
            <small>{formatShortDate(item.updatedAt || item.startedAt)}</small>
          </div>
        </article>
      ))}
    </div>
  );
}

function BarMetric({ label, value, max, tone = "blue" }) {
  const width = max ? Math.max((value / max) * 100, value ? 8 : 0) : 0;

  return (
    <div className="bar-metric">
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <div className="bar-track">
        <span className={`bar-fill ${tone}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function ActivityVelocityChart({ activityData, activityError, activityUser }) {
  const days = activityData?.days || [];
  const maxValue = Math.max(
    ...days.flatMap((day) => [day.commits, day.issues, day.pullRequests]),
    1
  );
  const hasActivity = days.some((day) => day.commits || day.issues || day.pullRequests);
  const heightFor = (value) => `${Math.max((value / maxValue) * 100, value ? 8 : 0)}%`;
  const userLabel = activityUser ? `@${activityUser}` : "the signed-in user";

  return (
    <article className="analysis-card velocity-card">
      <div className="analysis-heading">
        <span>Development velocity</span>
        <strong>Issues vs commits vs pull requests</strong>
      </div>
      <p className="analysis-copy">
        Daily GitHub activity for {userLabel} in the selected tenant.
      </p>
      {activityError && <p className="data-warning">{activityError}</p>}
      {!activityData && !activityError && (
        <EmptyState title="Loading activity" detail="Reading GitHub search activity for this user." />
      )}
      {activityData && !hasActivity && (
        <EmptyState title="No user activity found" detail="No issues, commits, or pull requests were returned for this date range." />
      )}
      {activityData && hasActivity && (
        <>
          <div className="velocity-legend" aria-label="Chart legend">
            <span><i className="legend-dot commits" />Commits</span>
            <span><i className="legend-dot issues" />Issues</span>
            <span><i className="legend-dot pull-requests" />Pull Requests</span>
          </div>
          <div className="velocity-scale">
            <span>0</span>
            <span>{maxValue}</span>
          </div>
          <div
            className="velocity-scroll"
            role="img"
            aria-label={`Daily commits, issues, and pull requests for ${userLabel}`}
          >
            <div className="velocity-chart">
              {days.map((day) => (
                <div key={day.date} className="velocity-day">
                  <div className="velocity-bars">
                    <span
                      className="velocity-bar commits"
                      style={{ height: heightFor(day.commits) }}
                      title={`${day.label}: ${day.commits} commits`}
                    />
                    <span
                      className="velocity-bar issues"
                      style={{ height: heightFor(day.issues) }}
                      title={`${day.label}: ${day.issues} issues`}
                    />
                    <span
                      className="velocity-bar pull-requests"
                      style={{ height: heightFor(day.pullRequests) }}
                      title={`${day.label}: ${day.pullRequests} pull requests`}
                    />
                  </div>
                  <small>{day.label}</small>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </article>
  );
}

function AnalyticsView({ role, incidents, onRefresh, activityData, activityError, activityUser }) {
  const analytics = analyticsForIncidents(incidents);
  const totals = activityData?.totals || { commits: 0, issues: 0, pullRequests: 0 };
  const workflowMax = Math.max(
    analytics.issueRows,
    analytics.prOnlyRows,
    analytics.linkedPrs,
    analytics.reviewRequests,
    1
  );
  const signalMax = Math.max(
    analytics.openPrs,
    analytics.draftPrs,
    analytics.mergedPrs,
    analytics.failingChecks,
    1
  );

  return (
    <div className="content-grid">
      <SectionHeader
        title="User Activity Analytics"
        subtitle={`Issues, commits, and pull requests created by ${activityUser ? `@${activityUser}` : "the signed-in user"} across the selected GitHub tenant.`}
        onRefresh={onRefresh}
      />

      <section className="analysis-summary" aria-label="User activity totals">
        <MetricCard label="Commits" value={totals.commits} />
        <MetricCard label="Issues created" value={totals.issues} />
        <MetricCard label="Pull requests" value={totals.pullRequests} />
        <MetricCard label={role === "Admin" ? "Visible bot rows" : "My bot rows"} value={incidents.length} />
      </section>

      <ActivityVelocityChart
        activityData={activityData}
        activityError={activityError}
        activityUser={activityUser}
      />

      {activityData?.errors?.length > 0 && (
        <p className="data-warning">
          GitHub returned partial activity data for some search requests. The chart shows the counts that were available.
        </p>
      )}

      <section className="analytics-grid" aria-label="Visible bot incident context">
        <article className="analysis-card">
          <div className="analysis-heading">
            <span>Visible bot work</span>
            <strong>{role === "Admin" ? "Tenant scope" : "Assigned or requested"}</strong>
          </div>
          <div className="bar-list">
            <BarMetric label="Issue rows" value={analytics.issueRows} max={workflowMax} tone="blue" />
            <BarMetric label="Standalone PR rows" value={analytics.prOnlyRows} max={workflowMax} tone="green" />
            <BarMetric label="Linked PRs" value={analytics.linkedPrs} max={workflowMax} tone="amber" />
            <BarMetric label="Review requests" value={analytics.reviewRequests} max={workflowMax} tone="neutral" />
          </div>
        </article>

        <article className="analysis-card">
          <div className="analysis-heading">
            <span>Pull request signals</span>
            <strong>Current GitHub states</strong>
          </div>
          <div className="bar-list">
            <BarMetric label="Open PRs" value={analytics.openPrs} max={signalMax} tone="blue" />
            <BarMetric label="Draft PRs" value={analytics.draftPrs} max={signalMax} tone="amber" />
            <BarMetric label="Merged PRs" value={analytics.mergedPrs} max={signalMax} tone="green" />
            <BarMetric label="Failing checks" value={analytics.failingChecks} max={signalMax} tone="danger" />
          </div>
        </article>
      </section>
    </div>
  );
}

function ArchitectureView({ onRefresh }) {
  return (
    <div className="content-grid">
      <SectionHeader
        title="Architecture reference"
        subtitle="UI currently renders the GitHub-backed issue, PR, review, check, and closure state from the provided architecture."
        onRefresh={onRefresh}
      />
      <section className="architecture-grid">
        <div className="architecture-notes">
          <h2>Dashboard mapping</h2>
          <ul>
            <li>GitHub issues become tenant incident rows.</li>
            <li>Linked PRs, requested reviewers, checks, and closure state appear in the incident view.</li>
            <li>Agent and telemetry stages will be added only after real event data is available.</li>
            <li>RBAC splits full tenant operations from user-scoped PR tracking.</li>
          </ul>
        </div>
        <div className="diagram-frame">
          <img src={architectureDiagram} alt="Agentic incident resolution architecture" />
        </div>
      </section>
    </div>
  );
}

function MetricCard({ label, value, tone }) {
  return (
    <article className={`metric-card ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function SectionHeader({ title, subtitle, onRefresh }) {
  return (
    <div className="section-header">
      <div>
        <div className="section-title-line">
          <h2>{title}</h2>
        </div>
        {subtitle && (
          <p className="section-guide">
            <span aria-hidden="true">i</span>
            <span>{subtitle}</span>
          </p>
        )}
      </div>
      {onRefresh && (
        <button className="icon-button" title="Refresh" aria-label="Refresh" onClick={onRefresh}>
          <RefreshIcon />
        </button>
      )}
    </div>
  );
}

function EmptyState({ title, detail }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  );
}

function IncidentRow({ incident, active, onClick }) {
  return (
    <article
      className={`incident-row ${active ? "active" : ""}`}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(event) => onCardKeyDown(event, onClick)}
    >
      <div className="incident-row-top">
        <strong>{incident.id}</strong>
        <LabelSummary labels={incident.labels} />
      </div>
      <span>{incident.title}</span>
      <div className="incident-row-bottom">
        <small>{incident.repo}</small>
        <small>
          {incident.issue ? (
            <GitHubNumberLink incident={incident} type="issue" />
          ) : (
            <GitHubNumberLink incident={incident} type="pr" fallback="PR only" />
          )}
        </small>
      </div>
    </article>
  );
}

function IncidentHeader({ incident, compact = false }) {
  return (
    <section className="incident-header">
      <div>
        <div className="incident-heading-line">
          <LabelSummary labels={incident.labels} />
          <Pill tone={statusTone(incident.status, incident.health)}>
            {incident.status}
          </Pill>
        </div>
        <h2>{incident.title}</h2>
        <p>{incident.impact}</p>
      </div>
      {!compact && (
        <div className="incident-stats">
          <div>
            <span>Linked PR</span>
            <strong>
              <GitHubNumberLink incident={incident} type="pr" prefix="" />
            </strong>
          </div>
        </div>
      )}
    </section>
  );
}

function fallbackProcessStep(stage, incident) {
  const checks = incident.checks || { passing: 0, total: 0, failingName: null };
  const hasPr = Boolean(incident.pr);
  const statusText = (incident.status || "").toLowerCase();
  const isMergedOrClosed =
    statusText.includes("merged") ||
    statusText.includes("closed") ||
    incident.health === "stabilizing";

  if (stage === "Issue") {
    return {
      stage,
      status: isMergedOrClosed ? "done" : "current",
      actor: "GitHub Issue",
      detail: `Issue #${incident.issue} in ${incident.repo}.`,
      time: incident.startedAt || "GitHub"
    };
  }

  if (stage === "Linked PR") {
    return {
      stage,
      status: hasPr ? (isMergedOrClosed ? "done" : "current") : "waiting",
      actor: "GitHub Pull Request",
      detail: hasPr
        ? `PR #${incident.pr} on ${incident.branch}.`
        : "No linked pull request was returned.",
      time: hasPr ? incident.startedAt || "GitHub" : "Pending"
    };
  }

  if (stage === "Review") {
    const reviewers = incident.reviewers || [];
    return {
      stage,
      status: hasPr ? (reviewers.length ? "current" : "waiting") : "waiting",
      actor: "Review Requests",
      detail: reviewers.length
        ? `Requested reviewers: ${reviewers.join(", ")}.`
        : "No requested reviewers were returned.",
      time: hasPr ? "GitHub" : "Pending"
    };
  }

  if (stage === "Checks") {
    const hasChecks = checks.total > 0;
    return {
      stage,
      status: !hasPr || !hasChecks ? "waiting" : checks.failingName ? "blocked" : "done",
      actor: "GitHub Checks",
      detail: hasChecks
        ? `${checks.passing}/${checks.total} checks passing${checks.failingName ? `; ${checks.failingName} is failing.` : "."}`
        : "No check runs or commit statuses were returned.",
      time: hasChecks ? "GitHub" : "Pending"
    };
  }

  return {
    stage,
    status: isMergedOrClosed ? "done" : "waiting",
    actor: "GitHub State",
    detail: hasPr
      ? `PR #${incident.pr} and issue #${incident.issue} closure state.`
      : `Issue #${incident.issue} closure state.`,
    time: isMergedOrClosed ? "GitHub" : "Pending"
  };
}

function ProcessTimeline({ incident }) {
  const stageMap = new Map((incident.timeline || []).map((item) => [item.stage, item]));

  return (
    <section className="process-board" aria-label="Incident process timeline">
      {stages.map((stage) => {
        const item = stageMap.get(stage) || fallbackProcessStep(stage, incident);
        return (
          <article key={stage} className={`process-step ${item.status}`}>
            <div className="process-step-top">
              <span>{item.time}</span>
            </div>
            <strong>{item.stage}</strong>
            <small>{item.actor}</small>
            <p>
              <LinkedProcessDetail detail={item.detail} incident={incident} />
            </p>
          </article>
        );
      })}
    </section>
  );
}

function LinkedProcessDetail({ detail, incident }) {
  const text = detail || "";
  const parts = text.split(/((?:PR|Issue|issue) #\d+)/g);

  return parts.map((part, index) => {
    const prMatch = part.match(/^PR #(\d+)$/);
    const issueMatch = part.match(/^(Issue|issue) #(\d+)$/);

    if (prMatch && Number(prMatch[1]) === Number(incident.pr)) {
      return <GitHubNumberLink key={`${part}-${index}`} incident={incident} type="pr" />;
    }

    if (issueMatch && Number(issueMatch[2]) === Number(incident.issue)) {
      return <GitHubNumberLink key={`${part}-${index}`} incident={incident} type="issue" />;
    }

    return part;
  });
}

function PullRequestTracker({ incident, full = false }) {
  const checkTone = incident.checks.passing === incident.checks.total ? "green" : "amber";

  return (
    <section className={`pr-tracker ${full ? "full" : ""}`}>
      <div className="pr-tracker-header">
        <div>
          <p className="eyebrow">GitHub pull request</p>
          <h2>
            <GitHubNumberLink incident={incident} type="pr" fallback="No linked PR" />: {incident.branch}
          </h2>
        </div>
        <Pill tone={checkTone}>
          {incident.checks.passing}/{incident.checks.total} checks
        </Pill>
      </div>

      <div className="tracker-grid">
        <article>
          <span>Repository</span>
          <strong>{incident.repo}</strong>
        </article>
        <article>
          <span>Issue</span>
          <strong>
            <GitHubNumberLink
              incident={incident}
              type="issue"
              prefix=""
              fallback="None linked"
            />
          </strong>
        </article>
        <article>
          <span>Reviewers</span>
          <strong>{incident.reviewers.length ? incident.reviewers.join(", ") : "None"}</strong>
        </article>
        <article>
          <span>Failing check</span>
          <strong>{incident.checks.failingName || "None"}</strong>
        </article>
      </div>

      <div className="label-row">
        <LabelSummary labels={incident.labels} max={2} />
      </div>
      <ProcessTimeline incident={incident} />
    </section>
  );
}

export default App;

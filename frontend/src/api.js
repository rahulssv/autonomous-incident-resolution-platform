import {
  auditEvents as mockAuditEvents,
  incidents as mockIncidents,
  sessionUser as mockSessionUser,
  tenants as mockTenants
} from "./mockGithubData.js";

const defaultApiBaseUrl = import.meta.env.DEV
  ? "http://127.0.0.1:8000"
  : window.location.origin;

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || defaultApiBaseUrl;

export const mockDashboardData = {
  source: "mock",
  sessionUser: mockSessionUser,
  tenants: mockTenants,
  incidents: mockIncidents,
  auditEvents: mockAuditEvents,
  summary: null
};

export async function fetchDashboardData(org, tenantId) {
  const url = new URL(`/api/github/orgs/${encodeURIComponent(org)}/dashboard`, API_BASE_URL);
  url.searchParams.set("state", "all");
  url.searchParams.set("limit", "100");

  const response = await fetch(url, { credentials: "include" });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `GitHub dashboard request failed with ${response.status}`);
  }

  const payload = await response.json();
  const tenant = payload.tenant
    ? {
        ...payload.tenant,
        id: tenantId || payload.tenant.id,
        githubOrg: payload.tenant.githubOrg || org
      }
    : null;

  return {
    ...payload,
    source: payload.source || "github",
    tenant,
    tenants: tenant ? [tenant] : payload.tenants || [],
    incidents: (payload.incidents || []).map((incident) => ({
      ...incident,
      tenantId: tenant?.id || incident.tenantId || tenantId || org,
      checks: incident.checks || { passing: 0, total: 0, failingName: null },
      labels: incident.labels || [],
      reviewers: incident.reviewers || [],
      reviewedBy: incident.reviewedBy || [],
      assignees: incident.assignees || [],
      mcpCalls: incident.mcpCalls || [],
      timeline: incident.timeline || []
    })),
    auditEvents: payload.auditEvents || []
  };
}

export async function fetchUserActivity(org, user, days = 21) {
  const url = new URL(`/api/github/orgs/${encodeURIComponent(org)}/user-activity`, API_BASE_URL);
  url.searchParams.set("user", user);
  url.searchParams.set("days", String(days));

  const response = await fetch(url, { credentials: "include" });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `GitHub user activity request failed with ${response.status}`);
  }

  return response.json();
}

export async function fetchResolutionStages() {
  const response = await fetch(`${API_BASE_URL}/api/graph/stages`, {
    credentials: "include"
  });
  if (!response.ok) {
    throw new Error(`Resolution stages request failed with ${response.status}`);
  }
  return response.json();
}

export async function fetchResolutionIncidents() {
  const response = await fetch(`${API_BASE_URL}/api/graph/incidents`, {
    credentials: "include"
  });
  if (!response.ok) {
    throw new Error(`Resolution incidents request failed with ${response.status}`);
  }
  return response.json();
}

export async function fetchResolutionIncident(incidentId) {
  const response = await fetch(
    `${API_BASE_URL}/api/graph/incidents/${encodeURIComponent(incidentId)}`,
    { credentials: "include" }
  );
  if (!response.ok) {
    throw new Error(`Resolution incident request failed with ${response.status}`);
  }
  return response.json();
}

export function buildResolutionStreamUrl({ scenario, severity, title }) {
  const url = new URL("/api/graph/demo-resolution", API_BASE_URL);
  url.searchParams.set("scenario", scenario);
  url.searchParams.set("severity", severity);
  if (title) {
    url.searchParams.set("title", title);
  }
  return url.toString();
}

export function buildIncidentResolutionStreamUrl(incidentId) {
  const url = new URL(
    `/api/graph/incidents/${encodeURIComponent(incidentId)}/stream`,
    API_BASE_URL
  );
  return url.toString();
}

export function beginGitHubLogin() {
  const url = new URL("/api/auth/github/login", API_BASE_URL);
  url.searchParams.set("return_to", window.location.origin);
  window.location.href = url.toString();
}

export async function fetchAuthSession() {
  const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
    credentials: "include"
  });
  if (!response.ok) {
    throw new Error(`Auth session request failed with ${response.status}`);
  }
  return response.json();
}

export async function logout() {
  await fetch(`${API_BASE_URL}/api/auth/logout`, {
    method: "POST",
    credentials: "include"
  });
}

export function authSessionToDashboard(authSession, currentDashboard = mockDashboardData) {
  if (!authSession?.authenticated) {
    return currentDashboard;
  }

  const orgs = authSession.user.organizations || [];
  const tenants = orgs.map((org) => ({
        id: org.id || org.githubOrg,
        name: org.name || org.githubOrg,
        plan: "GitHub",
        repositories: org.repositories || 0,
        githubOrg: org.githubOrg || org.id,
        url: org.url,
        avatarUrl: org.avatarUrl,
        membershipRole: org.membershipRole,
        membershipState: org.membershipState,
        source: org.source,
        installationId: org.installationId,
        repositorySelection: org.repositorySelection,
        appSlug: org.appSlug
  }));

  const firstTenant = tenants[0];
  return {
    ...currentDashboard,
    source: "github-auth",
    sessionUser: {
      name: authSession.user.name || authSession.user.login,
      handle: authSession.user.login,
      org: firstTenant?.name || "",
      tenant: firstTenant?.id || "",
      avatarUrl: authSession.user.avatarUrl,
      roles: ["Admin", "User"],
      teams: []
    },
    tenants,
    incidents: [],
    auditEvents: []
  };
}

export function mergeDashboardData(current, incoming, tenantId) {
  const incomingTenant = incoming.tenant;
  const tenants = incomingTenant
    ? current.tenants.map((tenant) =>
        tenant.id === tenantId ? { ...tenant, ...incomingTenant, id: tenant.id } : tenant
      )
    : current.tenants;

  const otherIncidents = current.incidents.filter((incident) => incident.tenantId !== tenantId);
  const otherEvents = current.auditEvents.filter((event) => event.tenantId !== tenantId);

  return {
    ...current,
    ...incoming,
    tenants,
    incidents: [...otherIncidents, ...incoming.incidents],
    auditEvents: [...otherEvents, ...incoming.auditEvents],
    sessionUser: current.sessionUser
  };
}

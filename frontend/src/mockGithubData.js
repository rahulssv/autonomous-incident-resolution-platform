export const sessionUser = {
  name: "Maya Rao",
  handle: "mrao",
  org: "Northstar Retail",
  tenant: "northstar-prod",
  teams: ["SRE", "Checkout"],
  roles: ["Admin", "User"]
};

export const tenants = [
  {
    id: "northstar-prod",
    name: "Northstar Retail",
    plan: "Enterprise",
    repositories: 42,
    githubOrg: "northstar-retail"
  },
  {
    id: "finops-prod",
    name: "FinOps Cloud",
    plan: "Enterprise",
    repositories: 28,
    githubOrg: "finops-cloud"
  }
];

export const stages = [
  "Issue",
  "Linked PR",
  "Review",
  "Checks",
  "Merge / Closure"
];

export const incidents = [
  {
    id: "INC-4821",
    tenantId: "northstar-prod",
    issue: 1842,
    pr: 1849,
    title: "Checkout latency above 500 ms after deploy",
    severity: "SEV-1",
    status: "Linked PR open",
    health: "active",
    service: "checkout-service",
    repo: "northstar-retail/checkout-service",
    branch: "agent/revert-payment-cache-timeout",
    owner: "Checkout SRE",
    assignee: "mrao",
    startedAt: "May 16, 2026 10:08",
    elapsed: "24m",
    confidence: 92,
    impact: "Payment authorization path is breaching customer checkout SLO in ap-south-1.",
    agentSummary:
      "GitHub shows a linked PR with a rollback patch and review requests.",
    mcpCalls: [
      "list_recent_commits",
      "get_pull_request_diff",
      "create_pull_request",
      "list_check_runs"
    ],
    checks: {
      passing: 5,
      total: 6,
      failingName: "payments-contract-test"
    },
    reviewers: ["app-platform", "payments-owner"],
    labels: ["incident", "agentic-remediation", "needs-human-approval"],
    timeline: [
      {
        stage: "Issue",
        status: "current",
        actor: "GitHub Issue",
        detail: "Issue #1842 is open with incident labels and assignee mrao.",
        time: "10:08"
      },
      {
        stage: "Linked PR",
        status: "current",
        actor: "GitHub Pull Request",
        detail: "PR #1849 is open on agent/revert-payment-cache-timeout.",
        time: "10:24"
      },
      {
        stage: "Review",
        status: "current",
        actor: "Review Requests",
        detail: "Requested reviewers: app-platform, payments-owner.",
        time: "10:24"
      },
      {
        stage: "Checks",
        status: "blocked",
        actor: "GitHub Actions",
        detail: "5 of 6 checks are passing; payments-contract-test is failing.",
        time: "10:30"
      },
      {
        stage: "Merge / Closure",
        status: "waiting",
        actor: "GitHub State",
        detail: "PR #1849 is open; issue #1842 is open.",
        time: "Pending"
      }
    ]
  },
  {
    id: "INC-4817",
    tenantId: "northstar-prod",
    issue: 1829,
    pr: 1836,
    title: "Inventory worker memory leak in west cluster",
    severity: "SEV-2",
    status: "PR merged",
    health: "stabilizing",
    service: "inventory-worker",
    repo: "northstar-retail/inventory-worker",
    branch: "agent/fix-batch-window-leak",
    owner: "Platform Ops",
    assignee: "akhan",
    startedAt: "May 16, 2026 09:34",
    elapsed: "58m",
    confidence: 86,
    impact: "Backlog for inventory sync was delayed for 11 stores.",
    agentSummary:
      "GitHub shows the linked PR was merged after checks passed.",
    mcpCalls: ["search_issues", "compare_commits", "merge_pull_request", "list_workflow_runs"],
    checks: {
      passing: 7,
      total: 7,
      failingName: null
    },
    reviewers: ["platform-ops"],
    labels: ["incident", "merged", "recovery-watch"],
    timeline: [
      {
        stage: "Issue",
        status: "done",
        actor: "GitHub Issue",
        detail: "Issue #1829 is closed with incident labels and assignee akhan.",
        time: "09:34"
      },
      {
        stage: "Linked PR",
        status: "done",
        actor: "GitHub Pull Request",
        detail: "PR #1836 was merged from agent/fix-batch-window-leak.",
        time: "10:08"
      },
      {
        stage: "Review",
        status: "done",
        actor: "Review Requests",
        detail: "Requested reviewers: platform-ops.",
        time: "10:08"
      },
      {
        stage: "Checks",
        status: "done",
        actor: "GitHub Actions",
        detail: "7 of 7 checks are passing.",
        time: "10:16"
      },
      {
        stage: "Merge / Closure",
        status: "done",
        actor: "GitHub State",
        detail: "PR #1836 is merged; issue #1829 is closed.",
        time: "10:16"
      }
    ]
  },
  {
    id: "INC-4808",
    tenantId: "finops-prod",
    issue: 771,
    pr: 779,
    title: "Settlement API 500s after schema migration",
    severity: "SEV-1",
    status: "Review requested",
    health: "active",
    service: "settlement-api",
    repo: "finops-cloud/settlement-api",
    branch: "agent/add-null-safe-ledger-field",
    owner: "Payments Platform",
    assignee: "mrao",
    startedAt: "May 16, 2026 10:18",
    elapsed: "14m",
    confidence: 79,
    impact: "Settlement preview endpoint is failing for enterprise tenants.",
    agentSummary:
      "Agent proposed a null-safe migration patch and is waiting for policy approval.",
    mcpCalls: ["get_issue", "list_recent_commits", "create_branch"],
    checks: {
      passing: 0,
      total: 0,
      failingName: "Not started"
    },
    reviewers: ["payments-platform"],
    labels: ["incident", "approval-required", "database"],
    timeline: [
      {
        stage: "Issue",
        status: "current",
        actor: "GitHub Issue",
        detail: "Issue #771 is open with incident labels and assignee mrao.",
        time: "10:18"
      },
      {
        stage: "Linked PR",
        status: "current",
        actor: "GitHub Pull Request",
        detail: "PR #779 is open on agent/add-null-safe-ledger-field.",
        time: "10:28"
      },
      {
        stage: "Review",
        status: "current",
        actor: "Review Requests",
        detail: "Requested reviewers: payments-platform.",
        time: "10:28"
      },
      {
        stage: "Checks",
        status: "waiting",
        actor: "GitHub Checks",
        detail: "No check runs or commit statuses were returned.",
        time: "Pending"
      },
      {
        stage: "Merge / Closure",
        status: "waiting",
        actor: "GitHub State",
        detail: "PR #779 is open; issue #771 is open.",
        time: "Pending"
      }
    ]
  }
];

export const auditEvents = [
  {
    id: "evt-601",
    tenantId: "northstar-prod",
    type: "RBAC",
    actor: "mrao",
    detail: "Viewed all tenant workflows as Admin.",
    time: "10:32"
  },
  {
    id: "evt-600",
    tenantId: "northstar-prod",
    type: "GitHub MCP",
    actor: "remediation-agent",
    detail: "create_pull_request returned PR #1849.",
    time: "10:24"
  },
  {
    id: "evt-599",
    tenantId: "northstar-prod",
    type: "Approval",
    actor: "checkout-sre",
    detail: "Approved rollback execution boundary for INC-4821.",
    time: "10:20"
  },
  {
    id: "evt-598",
    tenantId: "finops-prod",
    type: "Policy",
    actor: "rca-agent",
    detail: "Flagged database migration change for manual approval.",
    time: "10:28"
  }
];

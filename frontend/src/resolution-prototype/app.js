// Standalone prototype reference. The active React integration lives in App.jsx.
const stageList = document.querySelector("#stageList");
const eventLog = document.querySelector("#eventLog");
const startButton = document.querySelector("#startRun");
const scenarioInput = document.querySelector("#scenario");
const severityInput = document.querySelector("#severity");
const titleInput = document.querySelector("#title");
const runState = document.querySelector("#runState");
const incidentTitle = document.querySelector("#incidentTitle");
const incidentId = document.querySelector("#incidentId");
const incidentSeverity = document.querySelector("#incidentSeverity");
const incidentStatus = document.querySelector("#incidentStatus");
const detectionTitle = document.querySelector("#detectionTitle");
const detectionSource = document.querySelector("#detectionSource");
const detectionSignal = document.querySelector("#detectionSignal");
const detectionRoute = document.querySelector("#detectionRoute");
const detectionConfidence = document.querySelector("#detectionConfidence");
const activeStage = document.querySelector("#activeStage");
const stageSummary = document.querySelector("#stageSummary");
const metricEvents = document.querySelector("#metricEvents");
const metricTools = document.querySelector("#metricTools");
const metricModels = document.querySelector("#metricModels");
const rcaHypothesis = document.querySelector("#rcaHypothesis");
const evidenceRefs = document.querySelector("#evidenceRefs");
const documentationDraft = document.querySelector("#documentationDraft");

let stages = [];
let source = null;
let stageOutputs = new Map();

async function bootstrap() {
  try {
    const response = await fetch("/api/graph/stages");
    const payload = await response.json();
    stages = payload.items || [];
  } catch {
    stages = [
      { id: "monitoring", label: "Monitoring", agent: "Monitoring Agent" },
      { id: "correlation", label: "Correlation", agent: "Correlation Agent" },
      { id: "rca", label: "RCA", agent: "RCA Agent" },
      { id: "remediation", label: "Remediation", agent: "Remediation Agent" },
      { id: "documentation", label: "Documentation", agent: "Documentation Agent" },
      { id: "embedding", label: "Knowledge Capture", agent: "Documentation Memory" },
    ];
  }
  renderStages();
}

function renderStages() {
  stageList.innerHTML = "";
  stages.forEach((stage, index) => {
    const item = document.createElement("li");
    item.className = "stage-item";
    item.dataset.stage = stage.id;
    item.innerHTML = `
      <span class="stage-dot">${index + 1}</span>
      <span>
        <span class="stage-name">${escapeHtml(stage.label)}</span>
        <span class="stage-agent">${escapeHtml(stage.agent)}</span>
        <span class="stage-output">${escapeHtml(stage.output || "")}</span>
      </span>
    `;
    stageList.appendChild(item);
  });
}

function startResolution() {
  if (source) {
    source.close();
  }
  resetUi();
  const params = new URLSearchParams({
    scenario: scenarioInput.value,
    severity: severityInput.value,
  });
  const title = titleInput.value.trim();
  if (title) {
    params.set("title", title);
  }

  source = new EventSource(`/api/graph/demo-resolution?${params.toString()}`);
  setRunState("Resolving", "running");
  startButton.disabled = true;

  source.addEventListener("metadata", (event) => {
    const data = parseEvent(event);
    updateIncident(data.incident);
    updateDetection(data.incident, data.scenario);
    appendEvent(
      `Application identified ${scenarioDetails(data.scenario).signal} from AKS logs.`,
      "info",
    );
  });

  source.addEventListener("run_started", (event) => {
    const data = parseEvent(event);
    updateSnapshot(data.snapshot);
    setCurrentStage(stages[0]?.id);
    appendEvent(data.summary || "Incident resolution started.", "info");
  });

  source.addEventListener("stage_completed", (event) => {
    const data = parseEvent(event);
    stageOutputs.set(data.stage, data);
    markStageComplete(data.stage);
    setNextStage(data.stage);
    updateStageDetails(data);
    updateSnapshot(data.snapshot);
    updateRca(data);
    updateDocumentation(data);
    appendEvent(`${labelFor(data.stage)} completed. ${data.summary}`, "done");
  });

  source.addEventListener("run_completed", (event) => {
    const data = parseEvent(event);
    updateSnapshot(data.snapshot);
    setRunState("Resolved", "done");
    clearCurrentStage();
    appendEvent(data.summary || "Incident resolution completed.", "done");
    startButton.disabled = false;
    source.close();
    source = null;
  });

  source.addEventListener("resolution_error", (event) => {
    const data = parseEvent(event);
    setRunState("Error", "error");
    appendEvent(data.error || data.summary || "Resolution failed.", "error");
    startButton.disabled = false;
  });

  source.onerror = () => {
    setRunState("Interrupted", "error");
    appendEvent("Resolution connection interrupted.", "error");
    startButton.disabled = false;
    if (source) {
      source.close();
      source = null;
    }
  };
}

function resetUi() {
  stageOutputs = new Map();
  renderStages();
  eventLog.innerHTML = "";
  const details = scenarioDetails(scenarioInput.value);
  detectionTitle.textContent = `${details.signal} identified`;
  detectionSource.textContent = details.source;
  detectionSignal.textContent = details.signal;
  detectionRoute.textContent = details.route;
  detectionConfidence.textContent = details.confidence;
  incidentTitle.textContent = "Preparing incident context";
  incidentId.textContent = "-";
  incidentSeverity.textContent = "-";
  incidentStatus.textContent = "-";
  activeStage.textContent = "Starting";
  stageSummary.textContent = "Resolution lifecycle is initializing.";
  metricEvents.textContent = "0";
  metricTools.textContent = "0";
  metricModels.textContent = "0";
  rcaHypothesis.textContent = "RCA output will appear after runtime evidence is collected.";
  evidenceRefs.innerHTML = "";
  documentationDraft.textContent = "No resolution record yet.";
}

function updateIncident(incident) {
  if (!incident) return;
  incidentTitle.textContent = incident.title || "Untitled incident";
  incidentId.textContent = incident.incident_id || "-";
  incidentSeverity.textContent = incident.severity || "-";
  incidentStatus.textContent = incident.status || "-";
}

function updateDetection(incident, scenario) {
  const details = scenarioDetails(scenario);
  detectionTitle.textContent = `${details.signal} identified`;
  detectionSource.textContent = incident?.description || details.source;
  detectionSignal.textContent = details.signal;
  detectionRoute.textContent = details.route;
  detectionConfidence.textContent = details.confidence;
}

function markStageComplete(stageId) {
  const item = stageItem(stageId);
  if (item) {
    item.classList.remove("current");
    item.classList.add("complete");
  }
}

function setCurrentStage(stageId) {
  clearCurrentStage();
  const item = stageItem(stageId);
  if (item) {
    item.classList.add("current");
  }
}

function setNextStage(stageId) {
  const index = stages.findIndex((stage) => stage.id === stageId);
  const next = stages[index + 1];
  if (next) {
    setCurrentStage(next.id);
  }
}

function clearCurrentStage() {
  document.querySelectorAll(".stage-item.current").forEach((item) => {
    item.classList.remove("current");
  });
}

function stageItem(stageId) {
  return document.querySelector(`[data-stage="${CSS.escape(stageId)}"]`);
}

function updateStageDetails(data) {
  activeStage.textContent = labelFor(data.stage);
  stageSummary.textContent = data.summary || "Stage completed.";
}

function updateSnapshot(snapshot) {
  if (!snapshot) return;
  metricEvents.textContent = snapshot.agent_event_count ?? 0;
  metricTools.textContent = snapshot.tool_call_count ?? 0;
  metricModels.textContent = snapshot.model_call_count ?? 0;
}

function updateRca(data) {
  if (data.stage !== "rca") return;
  const hypotheses = data.update?.rca_hypotheses || [];
  const top = hypotheses[0];
  rcaHypothesis.textContent = top?.hypothesis || data.summary || "No hypothesis generated.";
  evidenceRefs.innerHTML = "";
  const refs = data.update?.rca_evidence_bundle?.evidence_sources || [];
  refs.forEach((ref) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = ref;
    evidenceRefs.appendChild(chip);
  });
}

function updateDocumentation(data) {
  if (data.stage !== "documentation") return;
  const report = data.update?.documentation_report;
  if (!report) return;
  documentationDraft.innerHTML = "";
  [
    ["Executive", report.executive_summary],
    ["Root Cause", report.root_cause_summary],
    ["Remediation", report.remediation_summary],
  ].forEach(([label, value]) => {
    const paragraph = document.createElement("p");
    paragraph.innerHTML = `<strong>${escapeHtml(label)}:</strong> ${escapeHtml(value || "-")}`;
    documentationDraft.appendChild(paragraph);
  });
}

function appendEvent(message, kind) {
  const entry = document.createElement("article");
  entry.className = `event-entry ${kind || ""}`.trim();
  const time = new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  entry.innerHTML = `<time>${time}</time><p>${escapeHtml(message || "")}</p>`;
  eventLog.prepend(entry);
}

function parseEvent(event) {
  try {
    return JSON.parse(event.data);
  } catch {
    return {};
  }
}

function labelFor(stageId) {
  return stages.find((stage) => stage.id === stageId)?.label || stageId || "Stage";
}

function setRunState(text, className) {
  runState.textContent = text;
  runState.className = `run-state ${className || ""}`.trim();
}

function scenarioDetails(scenario) {
  const details = {
    crashloop: {
      signal: "CrashLoopBackOff",
      route: "aks.kubeevents.raw",
      confidence: "High confidence",
      source: "KubeEvents reported BackOff and repeated container restarts.",
    },
    oom: {
      signal: "OOMKilled",
      route: "aks.kubeevents.raw",
      confidence: "High confidence",
      source: "KubeEvents reported container termination due to memory pressure.",
    },
    latency: {
      signal: "Latency spike",
      route: "aks.containerlogs.raw",
      confidence: "Medium confidence",
      source: "Application logs reported timeout errors above the service SLO.",
    },
  };
  return details[scenario] || details.crashloop;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

startButton.addEventListener("click", startResolution);
bootstrap();

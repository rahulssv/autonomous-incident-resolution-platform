# AIRP — 5 Minute Client Demo Narration

Single source of truth for the voice-over. `generate-voiceover.py` reads this file,
speaks every `NARRATION:` block, and ignores everything else.

Export clean text for any external TTS service with:

    python3 demo/generate-voiceover.py --text

## Written for the ear

- **Short sentences.** Prosody degrades over long clauses. Fragments are deliberate.
- **No em-dashes.** Engines disagree on whether to pause.
- **Numbers spelled out.** "Seventy-two percent", never "0.72".
- **No raw status strings.** "Can't pull its image", not `ImagePullBackOff`.
- **`*Asterisks*` mark stress.** Rendered by the `say` engine, stripped elsewhere.

Full shot list with tab setup and timings: `demo/shot-list.md`.

## Accuracy rules for this script

Every claim below is backed by code or by a measured run. Four claims from earlier
drafts were removed because the platform does not do them yet: similar-incident
retrieval during correlation, vector search over incident history (the table is
empty and embeddings are disabled), MTTR trend analytics, and `git blame` based
assignment. See `demo/README.md` for the full claim-to-source table. Do not
reinstate them without building them first — a technical buyer will ask.

---

## [00:00] Scene 1 — Cold open

**SCREEN:** Terminal, full screen, `kubectl get pods -n shopfast`. Hold still.

NARRATION:
Two in the morning. Your phone goes off.
Five services in your production namespace are down. Checkout can't pull its image.
Pricing is stuck in a crash loop. Something changed in the last thirty minutes, and
nobody knows what.
So an engineer wakes up, and opens six tools to find out.
That search is the *expensive* part. The fix is usually four lines.

---

## [00:26] Scene 2 — What AIRP is

**SCREEN:** Cut to the AIRP dashboard, incident list.

NARRATION:
This is AIRP. It runs that same search for you, in about a minute, and it shows
every source it used.
Let me show you a real incident. End to end. Right now.

---

## [00:40] Scene 3 — The cluster

**SCREEN:** Terminal (or k9s). There is no cluster view in the dashboard.
Move the cursor to the crash-looping pod row, once, then hold still.

NARRATION:
This is the customer's cluster. Five microservices and a frontend, deployed by Helm
from their own private repositories. That pod is crash-looping live, as we speak.
Nothing here is staged.

---

## [00:56] Scene 4 — The alert

**SCREEN:** Kafka UI at localhost:8085, topic airp.alerts.raw. Expand the newest
message and put the cursor on the `fingerprint` field. Trigger the demo incident
from a second terminal as this scene starts.

NARRATION:
Here's the raw alert landing in Kafka, exactly as it would from the monitoring you
already run. Prometheus. Instana. Azure Monitor.
Look at the fingerprint. We deduplicate on it, so one noisy alert never spawns ten
incidents.

---

## [01:15] Scene 5 — The incident and the timeline

**SCREEN:** Resolution console. Click the incident, let the stage rail advance
through Detection, Correlation, RCA, Remediation, Documentation, Knowledge Capture.
Do not speed this up.

NARRATION:
And this is where the on-call engineer actually lives.
The incident is already open. Detected, correlated and root-caused in about a
minute. *Nobody touched it.*
Here's the full timeline. Monitoring validated the signal. Correlation resolved it
to a service, a namespace, a pod and a repository. Then the root cause agent planned
what evidence it needed, and went and collected it. Pod state, events and rollout
history through a Kubernetes MCP server. Commits and pull requests through a GitHub
MCP server. Image metadata from the registry.
Six agents. One narrow job each. Orchestrated with LangGraph, and made durable with
Temporal, so if a node dies mid-investigation the work resumes where it stopped.

---

## [02:00] Scene 6 — The finding

**SCREEN:** RCA panel. Let the confidence scores and evidence links sit on screen.

NARRATION:
Here's what it found. Three ranked explanations, each with its evidence attached.
The leading one, at seventy-two percent confidence. The checkout container exceeded
its memory limit and was terminated. Second, at sixty-five. An image architecture
mismatch, introduced by the automated deployment job that runs every thirty minutes.
Look at what it's *naming*. A specific job. A specific image tag. It found those in
the cluster. Nobody wrote it a service map to read.

---

## [02:32] Scene 7 — Issue and pull request

**SCREEN:** GitHub issue tab, hold 3s, then the linked pull request; scroll to the
assignee in the sidebar. Check the repo name matches the service in the narration.

NARRATION:
The agent has already opened this issue in the customer's repository.
And here's the fix, drafted as a pull request. The assignee isn't random. AIRP looks
up the most recent commit on each file it wants to change, and assigns the engineer
who last touched that code.
Nothing is merged. Nothing is deployed. It's a draft, waiting for a human.

---

## [02:58] Scene 8 — Slack

**SCREEN:** Slack notification with the summary and links.

NARRATION:
At the same moment, on-call gets a Slack message. The summary, the severity, and
direct links back into the incident. No tab hunting.

---

## [03:11] Scene 9 — Access control

**SCREEN:** Role switch in the top bar. Admin to User. The heading changes from
"Incidents" to "My Assigned Incidents" and the list shortens. Switch back after.

NARRATION:
And access control. Admins see every incident and every agent. Users see only what's
assigned to them. Those roles come from real GitHub organization membership, checked
against the org itself, not a checkbox in a settings page.

---

## [03:28] Scene 10 — The audit trail

**SCREEN:** No audit view exists. Stay on the Resolution console (Evidence and AI
Calls counters), then cut to a terminal running the audit export. Do NOT open
Analytics — it is User Activity Analytics and will invite the wrong question.

NARRATION:
For leadership, a complete audit trail. Every agent action. Every tool call with its
latency. Every model call with its prompt version and a fingerprint of its response.
Exportable, so a conclusion from today can be defended next year.

---

## [03:47] Scene 11 — Why this wins

**SCREEN:** Back to camera, or the Architecture view. Slow down.

NARRATION:
I want to be clear about what you just saw. Three things.
Experience. One console instead of seven browser tabs, built around how on-call
engineers actually work, with role-aware views and Slack where they already are.
Architecture. Multi-agent orchestration with LangGraph. MCP servers bridging your
clusters and your source code. Temporal for durability. IBM models throughout, so
your code and your incident data *never* leave your tenancy.
And the economics. The expensive part of an incident is the search, and the search
is what this removes. Every incident it handles leaves a written record behind, so
what your seniors know compounds in the platform instead of leaving with them.

---

## [04:32] Scene 12 — Close

**SCREEN:** Return to the ranked hypotheses. Hold, then fade.

NARRATION:
Point it at one namespace, and a handful of alerts you already trust yourselves to
diagnose. Run it beside your on-call, in observe-only mode. Compare its answer to
theirs, incident by incident.
It earns write access, or it doesn't.

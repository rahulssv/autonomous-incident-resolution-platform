# AIRP Client Demo — Runbook

Everything needed to record or present the five-minute demo.

| Asset | Path |
|---|---|
| Narration script (single source of truth) | `demo/narration-script.md` |
| Voice-over renderer | `demo/generate-voiceover.py` |
| Rendered audio | `demo/voiceover/` (gitignored — regenerate locally) |

Rendered speech is about **4 minutes 25 seconds**. The remaining ~35 seconds are
deliberate silence between scenes so the UI has room to breathe. Do not fill it.

---

## Pre-flight — do this the day before, not an hour before

### 1. The API container will not start without Entra credentials

`AIRP_AUTH_ENABLED=true` with an empty `AIRP_ENTRA_TENANT_ID` / `AIRP_ENTRA_CLIENT_ID`
is refused at startup by design — an API in that state 401s every request and no
token can ever be minted, so it fails loudly instead of silently.

```bash
# .env
AIRP_ENTRA_TENANT_ID=<tenant>
AIRP_ENTRA_CLIENT_ID=<client>
```

The dashboard reads Postgres directly and will demo fine without the API, but a
container in `Exited (1)` is the first thing a technical buyer notices in
`docker ps`. Fix it before you are on a call.

### 2. Seed the service catalog, or GitHub evidence stays empty

With `services` empty, correlation guesses the repository from the service name:
`checkout-worker` becomes `https://github.com/AIRP-client/checkout-worker`, which
does not exist. The real repository is `s1-checkout`. Every GitHub lookup 404s and
the RCA loses an entire evidence source.

Seeding the mapping (`s1-checkout`, `s2-inventory`, `s3-pricing`, `s4-payment`,
`s5-recommendation`, `frontend`) is the single highest-impact thing you can do
before the demo. The RCA is already strong without it — it is materially stronger
with commit and pull request history attached.

### 3. Bring the stack up with the kind overlay

The base compose file has no kind wiring, so Kubernetes evidence falls back to
fixtures and the RCA reports `namespace is unavailable`.

```bash
./scripts/vendor-bob.sh                      # Bob CLI into the image
./scripts/kind-kubeconfig.sh shopfast-local  # container-reachable kubeconfig
docker-compose build
docker-compose -f docker-compose.yml -f docker-compose.kind.yml up -d
```

### 4. Rehearse one full incident end to end

```bash
.venv/bin/python scripts/create-incident.py --scenario oom
```

Watch it reach `documentation` in the dashboard. The first Bob call of a session is
the slowest; run one throwaway incident so the demo incident is not the cold one.

### 5. Pre-flight checklist

```bash
docker ps --format '{{.Names}}\t{{.Status}}' | grep autonomous   # nothing Exited
kubectl get pods -n shopfast                                     # the broken state
open http://localhost:8000                                       # dashboard loads
```

---

## Recording

Start here:

```bash
python3 demo/generate-voiceover.py --check     # which engines this machine can use
```

### The stock macOS voices will sound robotic. This is not fixable by tuning.

macOS ships two generations of voice. Alex, Samantha, Fred and Victoria predate
neural synthesis — they differ in timbre but share one flat prosody model, which is
why switching between them changes the voice without changing the delivery. The
generator inserts sentence pauses and emphasis to get the most out of them, but
there is a hard ceiling. Pick one of these before recording:

| Option | Cost | Quality | Setup |
|---|---|---|---|
| Premium macOS voice | Free, offline | Large jump | System Settings > Accessibility > Spoken Content > System Voice > Manage Voices → Ava, Zoe, Evan or Serena (Premium) |
| `--engine openai` | Cents per render | Best, directable | `export OPENAI_API_KEY=...` |
| `--engine watson` | IBM Cloud service | Expressive neural | `export WATSON_TTS_APIKEY=... WATSON_TTS_URL=...` |

```bash
python3 demo/generate-voiceover.py --voice "Ava (Premium)"          # after downloading
python3 demo/generate-voiceover.py --engine openai --voice onyx     # most expressive
python3 demo/generate-voiceover.py --engine watson                  # keeps it all IBM
```

For this client in particular, **Watson is worth the setup**. The narration says the
platform runs on IBM models; a client will notice if the voice does too.

`--engine openai` accepts `--tone` — free-text delivery direction passed to the
model ("confident, warm and measured, never breathless"). It is the only engine that
takes acting notes.

### Pacing

Emphasis is authored in the script with `*asterisks*` and rendered as stress. The
generator reports the **measured** duration of every scene after rendering, not just
an estimate, because each voice has its own native pace — macOS voices run near 175
wpm and will come in short. Use `--rate` to correct:

```bash
python3 demo/generate-voiceover.py --rate 150   # 4m38s measured, lands near 5:00 in the edit
```

Aim for 4m30s–5m00s of speech. The remainder is deliberate silence between scenes.

Record screen capture per scene rather than one continuous take. The per-scene audio
files line up one-to-one, so a scene that goes wrong is re-recorded on its own.

### Scene-by-scene capture

| Scene | Screen | Note |
|---|---|---|
| 1 Cold open | Terminal, `kubectl get pods -n shopfast` | Hold still. Let the failures read. |
| 2 What AIRP is | Dashboard incident list | |
| 3 Live environment | Split: kubectl / dashboard | Sells that it is real |
| 4 Alert to incident | Terminal trigger, cut to dashboard | |
| 5 Agent pipeline | Dashboard resolution view | **Do not speed up.** Real latency is the point. |
| 6 The result | RCA panel, zoomed | Highlight confidence + evidence refs |
| 7 Trust | Audit trail, approval gate | |
| 8 Architecture | Architecture diagram | `architecture/` |
| 9 Close | RCA panel | Hold on the ranked hypotheses |

---

## Fallbacks

**The cluster misbehaves on the day.** `scripts/create-incident.py --scenario oom`
publishes a synthetic alert through the real pipeline. Everything downstream —
agents, evidence, RCA — is genuine. Have it ready in a second terminal.

**A Bob call is slow.** Scene 5 narration explicitly frames the wait as durable
execution. Let it run; do not cut away.

**RCA escalates instead of concluding.** It escalates below
`AIRP_RCA_MIN_HYPOTHESIS_CONFIDENCE` (default 0.4). This is a feature, and worth
narrating as one: the system refuses to assert a conclusion it cannot support. Do
not lower the threshold to force a clean result — a buyer who later discovers you
tuned it will discount everything else.

---

## What the demo claims, and what backs it

Every figure in the narration came from a real run against the live cluster. The
script deliberately contains **no invented metrics** — no MTTR reduction percentage,
no cost-per-incident figure. If the client asks for those, give them a pilot rather
than a number you cannot source.

| Claim in narration | Where it comes from |
|---|---|
| Six agents, narrow jobs | `LangGraphSupervisor._build_graph` — monitoring, correlation, rca, remediation, documentation, embedding |
| Detected to root cause "in about a minute" | Measured: 45s and 71s on incidents `ab1473c9` and `656744c5`. Full pipeline to documentation runs about two minutes. |
| Deduplicated on fingerprint | `messaging/dedupe.py`, `AIRP_ALERT_DEDUPE_TTL_SECONDS` |
| Kubernetes / GitHub MCP servers | `integrations/kubernetes_mcp/`, `integrations/github_mcp/` |
| Read-only investigation | MCP clients expose read verbs only; writes are separate approval-gated activities |
| Durable, resumes after node loss | Temporal workflow in `src/airp/workflows/` |
| Three hypotheses at 0.72 / 0.65 / 0.40 | Real RCA output, incident `656744c5` |
| Names the cron job and image tag | Live Kubernetes evidence via kubernetes-mcp |
| Issue opened in the repo | `github_artifacts` — 26 issues, 4 pull requests created to date |
| Assignee is the last committer of the file | `_github_pr_assignee` → `lookup_file_commits`, falling back to the latest repository commit |
| Slack message to on-call | `integrations/slack/`, `slack_messages` — 126 delivered |
| Roles from GitHub org membership | `frontend/backend/app/github_service.py` `_backfill_membership_roles` |
| Audit trail, exportable | `model_calls`, `tool_calls`, `incident_events`, `/api/incidents/{id}/audit/export` |
| Uncited claims rejected | `RCAAgent._ground_hypothesis_result` |
| Low confidence escalates | `AIRP_RCA_MIN_HYPOTHESIS_CONFIDENCE` |
| Secrets stripped before prompts | `integrations/genaihub/redaction.py` |
| Approval before any change | `approvals` table, `ExternalActionPolicy` |
| IBM models via Bob | `integrations/genaihub/bob_cli_client.py` |

### Claims removed, and why

Do not put these back without building them first. Each is the kind of thing a
technical buyer asks a follow-up question about.

| Removed claim | Reality |
|---|---|
| "Correlation found two similar incidents from last quarter" | Correlation resolves service, namespace, pod and repository. It performs no historical lookup. `/api/search/incidents` is a text query, not similarity, and is not called during the flow. |
| "Vector RAG over historical incidents" | `incident_embeddings` holds **0 rows**. `AIRP_EMBEDDING_ENABLED=false`, and Bob exposes no embeddings endpoint, so no provider is configured. |
| "Analytics: MTTR trends, recurring failure modes" | The analytics view is titled **User Activity Analytics**. No MTTR trend and no failure-mode clustering exists. |
| "MTTR goes from hours to minutes" | No baseline has been measured for this client. Offer a pilot instead of a number. |
| "Assignee from git blame history" | It is the most recent commit author on the file, not blame of the offending lines. Close, but a reviewer will catch the difference. |
| "Root-caused in under 30 seconds" | Measured at 45 to 71 seconds. "About a minute" is defensible; thirty is not. |
| "Five agents" | The graph has six nodes. |

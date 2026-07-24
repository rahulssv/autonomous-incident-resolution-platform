# AIRP Demo — Shot List

One row per narration scene. Durations are the measured length of that scene's
voice-over, so each screen action has to fit inside its own budget.

The dashboard has exactly five views: **Resolution · Incidents · Pull Requests ·
Analytics · Architecture**. There is no cluster view and no audit view — anything
outside those five comes from a terminal, Kafka UI, GitHub or Slack.

## Tab and window setup, before you hit record

Arrange these once and never fumble mid-take.

| # | Window | What is on it |
|---|---|---|
| 1 | Terminal, large font (16pt+) | `kubectl get pods -n shopfast` already run, output visible |
| 2 | Terminal, second tab | The incident trigger command, typed but **not** entered |
| 3 | Browser tab | `http://localhost:8085` — Kafka UI, on the `airp.alerts.raw` topic |
| 4 | Browser tab | `http://localhost:8000` — AIRP dashboard, Resolution view, logged in as Admin |
| 5 | Browser tab | The GitHub issue for your demo incident |
| 6 | Browser tab | The linked pull request |
| 7 | Slack | `#airp-alerts`, scrolled to the latest AIRP message |

Hide bookmarks, notifications and anything personal. Zoom the browser to 125% —
the dashboard reads small on video.

---

## The shots

### Scene 1 · Cold open · 29s
**Window 1 — terminal, full screen.**

`kubectl get pods -n shopfast`, output already on screen before the audio starts.
Do not type. Do not move the cursor. A completely still frame under the "two in the
morning" line is what sells it.

The pod list should show the crash-loop and image-pull failures. If the cluster has
self-healed since, that is fine — any red state works, but re-record this frame
rather than narrating failures that are not visible.

### Scene 2 · What AIRP is · 15s
**Window 4 — dashboard, Resolution view.**

Cut straight in. No transition. Land on the Resolution console with the
"Unresolved Incidents" list visible on the left. Do not click anything yet — this
scene is the reveal, and the line "let me show you a real incident" is the setup for
the next one.

### Scene 3 · The cluster · 14s
**Window 1 — terminal.**

Back to the pod list. Move the cursor to the crash-looping pod row as you say "that
pod is crash-looping live". One deliberate movement, then still again.

> If you have `k9s` installed, use it here instead. A live-updating TUI is visibly
> more alive than static `kubectl` output, and it reinforces "nothing here is
> staged". Do not install it for the first time on demo day.

### Scene 4 · The alert · 17s
**Window 3 — Kafka UI, `airp.alerts.raw`.**

Open the newest message and expand its JSON. Put the cursor on the `fingerprint`
field as the narration names it. That field is the whole point of the shot: it is
what dedupe keys on.

Trigger the incident from Window 2 at the *start* of this scene so the pipeline is
already running by Scene 5. Cut away before the terminal shows anything.

### Scene 5 · The incident and the timeline · 51s
**Window 4 — Resolution console. Your longest scene, and the most important.**

Click the incident in "Unresolved Incidents". Then, slowly:

1. Let the stage rail advance. Stages are Detection, Correlation, RCA, Remediation,
   Documentation, and Knowledge Capture.
2. Scroll to the "Current Phase" panel. The Evidence and AI Calls counters are
   visible here — let them land as you say "went and collected it".
3. Stay on screen while the phases complete.

**Do not speed this up or cut around the wait.** The narration explicitly frames the
latency, and a buyer who sees a real system taking a real minute trusts it more than
one that appears instant.

### Scene 6 · The finding · 34s
**Window 4 — RCA panel, zoomed.**

Scroll to the "RCA / Hypothesis" panel. Zoom the browser one more step so the
confidence figures are unmistakable. Move the cursor down the ranked list as each
one is named in the audio: seventy-two, then sixty-five.

On "look at what it's naming", highlight the job name and image tag by selecting
that text with the cursor. Selection reads better on video than a hover.

### Scene 7 · Issue and pull request · 27s
**Windows 5 and 6 — GitHub.**

Switch to the issue tab as "already opened this issue" is spoken. Give it three
seconds. Then the pull request tab. Scroll to the assignee in the sidebar as the
narration explains how it was chosen.

> **Continuity check.** Your existing artifacts are on `s3-pricing` and
> `s5-recommendation`, for example issue `s3-pricing/issues/1051` and PR
> `s5-recommendation/pull/1074`. The narration is about *checkout*. Either run the
> demo incident against a service that will produce matching artifacts, or record
> this scene from an incident whose issue and PR match the story. A client who
> notices the service name change will assume the demo is stitched together.

### Scene 8 · Slack · 11s
**Window 7 — Slack, `#airp-alerts`.**

Show the message. That is the entire shot. Eleven seconds is one beat — resist
scrolling the channel history.

> Messages are delivered by webhook, so there is no permalink back from the
> dashboard. Show Slack itself; do not promise a click-through that does not exist.

### Scene 9 · Access control · 17s
**Window 4 — the role switch in the top bar.**

Switch from Admin to User. The heading changes from "Incidents" to "My Assigned
Incidents", and the list shortens. That change *is* the shot — make sure both states
are on screen long enough to compare.

Switch back to Admin before the next scene.

### Scene 10 · The audit trail · 18s
**Window 4 — Resolution console, plus a terminal.**

There is no audit view in the dashboard. The audit trail is real and complete, but
it lives in the API and the database, not the UI. Two honest options:

- **Preferred.** Stay on the Resolution console showing the Evidence and AI Calls
  counters, then cut to a terminal showing the export:
  `curl .../api/incidents/<id>/audit/export`. Raw JSON scrolling past reads as
  substance to a technical buyer.
- **Simpler.** Stay on the Resolution Record panel and narrate the audit as a
  capability without showing it.

Do not click "Analytics" here. That view is **User Activity Analytics** — it does
not show MTTR or failure modes, and opening it while talking about audit invites
exactly the question you do not want.

> The audit API requires auth, so the API container must be running with Entra
> credentials set. If it is not, use the simpler option — or record this scene from
> a `psql` query against `model_calls`.

### Scene 11 · Why this wins · 49s
**Back to camera, or the Architecture view.**

Two choices. To camera is stronger if you are comfortable on video — this is the
persuasion beat and a face outperforms a diagram. Otherwise open the **Architecture**
view and move down it as each of the three points is named: experience,
architecture, economics.

Whichever you pick, slow down. This scene has the second-highest word count but
should feel like the least rushed.

### Scene 12 · Close · 18s
**Window 4 — RCA panel, ranked hypotheses.**

Return to the finding. Hold completely still on "it earns write access, or it
doesn't", then fade. No cursor movement in the final eight seconds.

---

## Total

| Scene | Screen | Duration |
|---|---|---|
| 1 Cold open | Terminal, pod list | 29s |
| 2 What AIRP is | Dashboard, Resolution | 15s |
| 3 The cluster | Terminal, pod list | 14s |
| 4 The alert | Kafka UI | 17s |
| 5 Timeline | Dashboard, Resolution | 51s |
| 6 The finding | Dashboard, RCA panel | 34s |
| 7 Issue and PR | GitHub | 27s |
| 8 Slack | Slack | 11s |
| 9 Access control | Dashboard, role switch | 17s |
| 10 Audit trail | Dashboard + terminal | 18s |
| 11 Why this wins | Camera or Architecture | 49s |
| 12 Close | Dashboard, RCA panel | 18s |

Speech totals 4m59s. Add roughly two seconds of silence between scenes in the edit
and the finished video lands near 5m20s.

## Screens deliberately not used

| Screen | Why |
|---|---|
| Analytics view | It is User Activity Analytics. Showing it while claiming operational insight invites a question with no good answer. |
| Pull Requests view | Overlaps Scene 7 and adds a nav click for no new information. |
| Temporal UI | Not exposed in `docker-compose.yml`. Durability is narrated, not shown. |
| Incidents (workflow) view | The Resolution console tells the story better. Use it only if you need to show incident volume. |

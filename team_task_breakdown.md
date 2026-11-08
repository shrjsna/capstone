# Team Task Breakdown — Industrial Safety Monitoring System
### Edge-Cloud Collaborative AI System for Real-Time Video Analytics — Team 47

This document expands the one-line assignments in README.md into a full
technical brief per person, based on every architectural decision made
for this project. Read the "System Overview" section first — it applies
to everyone — then jump to your section.

---

## System Overview (everyone reads this first)

### The product, in one line
One industrial safety camera system that detects PPE violations and
restricted-zone intrusions, and gets smarter about how it alerts over
time by learning from real operator feedback — without needing manual
threshold tuning, without full retraining cycles, and without raw video
ever leaving a deployment site.

### Why this design, not just "YOLO detects stuff"
Plain PPE/zone detection is a saturated, unoriginal capstone space. What
makes this project different is that the **decision-making itself is
adaptive** (via a self-maintaining bandit, not fixed thresholds), it's
**federated** (privacy-relevant for industrial video), and it's
**privacy-preserving by design** (faces blurred before any data leaves a
site). These three things are the actual novelty — the detectors
themselves are necessary infrastructure, not the point.

### Full architecture

```
EDGE (Jetson Nano, per site/camera)
 |- Module A: PPE detection (YOLOv11n) ---------------\
 |- Module B: Zone intrusion                           |
 |    (RT-DETR/YOLOv11n + ByteTrack                     |
 |     + polygon zone-check + debounce)  ---------------|--> Detection Event (JSON)
 |                                                       |
 |- Face-blur pass on any captured clip                 |
 |    (before clip ever leaves the device)               |
 |                                                       |
 \- (if event flagged) 10-sec clip captured              |
     (5s before / 5s after), blurred, reduced            |
     resolution/fps, trigger-based only                  |
                                                          v
CLOUD (FastAPI backend, per site)
 |- Module C: Contextual bandit (INFERENCE)  --> escalate / log / adjust-threshold --> alert
 |- (optional) I3D/Video Swin temporal anomaly  --> behavior score on captured clip
 |    scoring -- nice-to-have, cut first if squeezed
 |- Module D: Dashboard --> operator Confirm/False-Alarm --> reward signal logged
 \- Module D: Scheduled incremental bandit update
      --> validate vs held-out set --> version --> push to edge
                                                          v
FEDERATED LAYER (Flower/FedAvg, weekly, cross-site)
 \- Local policy weights ONLY (never raw data/video/logs)
      --> FedAvg aggregation --> global policy --> redistributed to all sites
```

### The shared contract: INTERFACES.md
This file at the repo root defines the exact JSON shape for:
1. **Detection Event** (A and B both emit this) — `camera_id`, `zone_id`,
   `event_type` (`"ppe_violation"` or `"zone_intrusion"`), `class`,
   `confidence`, `tracked_id`, `timestamp`, `frame_count_triggered`,
   `clip_captured`.
2. **Operator Feedback** (D emits from the dashboard, C consumes as its
   reward signal) — `event_id`, `feedback` (`"confirmed"` or
   `"false_alarm"`), `operator_id`, `timestamp`.
3. **Bandit Decision Output** (C emits, D consumes for the dashboard) —
   `event_id`, `action`, `policy_version`, `threshold_used`.
4. **Policy Update Record** (C/D, for versioning/rollback) —
   `policy_version`, `trained_at`, `validation_score`,
   `previous_version`, `deployed`.

**Nobody changes this file alone.** If your module needs a new field,
open a PR to INTERFACES.md by itself, get a thumbs-up from the other
three in the group chat, then build against the new shape.

### Repo-wide rules (from CONTRIBUTING.md)
- Branch off `dev`, name it `feature/<your-module>-<short-desc>`.
- Never push directly to `dev` or `main` — both are protected (PR + 1
  review + passing CI required).
- Every PR needs tests under `tests/` that run without needing a GPU,
  camera, or real trained weights (CI is CPU-only). Mock/stub hardware
  dependencies.
- Never commit datasets, raw video, model weights (`.pt`/`.onnx`), or
  `runs/` training output — `.gitignore` already blocks these; verify
  with `git status` before every commit.
- Log material design decisions in `docs/decisions.md` (dated, with
  reasoning) — this becomes your report/viva evidence trail.

---

## Person A — PPE Compliance Detection (reference implementation, already built)

This module is done and serves as the template for B's structure. Quick
recap of what's already decided and why, useful context for B/C/D:

- **Model:** YOLOv11n, fine-tuned — chosen over YOLO26 because YOLOv11
  wins specifically at nano/small scale (Jetson Nano constraint); YOLO26
  only wins at larger scales this project can't afford on edge hardware.
- **Dataset:** merged from 4 sources into one unified 16-class scheme
  (`prepare_dataset.py`), with per-class instance counts verified via
  `count_classes.py` — don't assume a class works just because it's in
  the label list; check its actual training volume.
- **Known, accepted limitation:** `no_boots` and `no_goggles` remain
  weak (mAP50 ~0.0-0.5) due to genuine data scarcity (as few as ~100
  training instances vs 5,000+ for working classes) — documented in
  `docs/decisions.md`, not something further modules need to fix.
- **Inference (`infer.py`):** uses `model.track(tracker="bytetrack.yaml")`
  for persistent IDs, a `DebounceTracker` class requiring 3 consecutive
  frames before firing an event, emits Detection Events matching
  INTERFACES.md, works standalone (local JSONL log) before the backend
  exists, and POSTs to `--api-url` once Module D's endpoint is live.

---

## Person B — Restricted Zone Intrusion Detection

### What this module does
Detects when a tracked person enters a restricted/hazardous zone and
emits a Detection Event — same schema as Person A's output, different
`event_type`/`class`. This is NOT a separate product from PPE detection;
it's the second "sense" feeding the same decision layer.

### Technical components, in order

**1. Detection + tracking**
- **RT-DETR** preferred (transformer-based, NMS-free — more novel for
  the report than plain YOLO) or **YOLOv11n** as a lighter, safer
  fallback if Jetson Nano compute proves too tight for RT-DETR in
  practice.
- **ByteTrack** for multi-object tracking — gives each detected person a
  persistent ID across frames. Without this, a person briefly at a zone
  boundary triggers repeated false alerts as detection flickers.
- Reuse Person A's pattern: Ultralytics' built-in
  `model.track(tracker="bytetrack.yaml", persist=True, stream=True)` —
  same API, no need to hand-roll ByteTrack integration.

**2. Zone definition (pure geometry, no ML)**
- One config file per camera (e.g. `zones/camera_01_zones.json`)
  defining the restricted area as a polygon in pixel coordinates.
- Drawn/defined once per camera install. A simple zone editor UI is
  nice-to-have (coordinate with Person D if dashboard time allows) —
  otherwise hand-authored JSON is completely fine for the demo.

**3. Zone-check logic**
- For each tracked person's box, compute a reference point (centroid or
  foot-point — foot-point is more accurate for "standing in a zone" than
  centroid, since a tall person's centroid may sit outside the zone
  while their feet are inside it).
- Point-in-polygon test against the camera's zone config.

**4. Debounce (same concept as Module A)**
- Require the intrusion signal for **3-5 consecutive frames** before
  firing an event. This alone removes a large share of false positives
  from momentary boundary crossings, at near-zero latency cost.
- Structure this the same way Person A's `DebounceTracker` works —
  keyed on `(track_id, class)`, resets when the track/class disappears
  from a frame. Literally reuse/import that class if it's generic enough,
  rather than reimplementing it — ask Person A.

**5. Emit events matching INTERFACES.md**
```json
{
  "camera_id": "cam_02",
  "zone_id": "zone_red_1",
  "event_type": "zone_intrusion",
  "class": "person_in_zone",
  "confidence": 0.91,
  "tracked_id": "person_37",
  "timestamp": "2026-09-07T10:15:00Z",
  "frame_count_triggered": 4,
  "clip_captured": true
}
```

**6. Clip capture for flagged events**
- When an intrusion event fires, capture a 10-second window (5s before
  + 5s after) at reduced resolution/fps (e.g. 224x224, 8-16fps —
  matches what a temporal model would need anyway).
- **Face-blur this clip before it's stored or leaves the device** —
  coordinate with Person A/D on which of you owns the shared
  face-blurring utility (YuNet or RetinaFace-nano) so it isn't
  implemented twice differently.
- Trigger-based capture only — never continuous recording — to keep
  storage bounded and support the "best-effort automated anonymization"
  privacy framing in the report.

**7. Optional, nice-to-have, cut first if squeezed: temporal anomaly scoring**
- I3D or Video Swin Transformer, running cloud-side (not edge — too
  heavy for Jetson Nano), scoring the captured clip for *behavior*
  (lingering, erratic movement) rather than just presence.
- This is explicitly lower priority than getting core detection + zone
  logic + debounce working end-to-end. If time is short, document it as
  "future work" in the report rather than shipping a half-working
  version.

### Demo strategy for this module specifically
- Stage real footage: tape off a "zone" in a hallway/lab, record people
  crossing it, run live detection on your actual Jetson Nano setup for
  the review demo — far more convincing live than any simulation.
- Be upfront in the report that this is staged/simulated rather than a
  real industrial deployment — completely normal and expected at
  capstone stage, and safer than overclaiming.

---

## Person C — Contextual Bandit Decision Layer (the core novelty)

### What this module does and why it exists
Sits between the two detectors (A, B) and the alert dashboard. Instead
of fixed thresholds, it **decides** how to respond to each incoming
event, and **adapts that decision-making over time** from real operator
feedback — this is what makes the system "self-maintaining," the
headline novelty of the whole capstone.

### Why contextual bandit, not DQN (already decided — don't relitigate this)
Alert decisions here (escalate / log / adjust-threshold) are
**single-step** — today's decision doesn't meaningfully change tomorrow's
state in a sequential-planning sense. A full DQN would model multi-step
dependencies you don't actually have, at a much higher training/update
cost. A contextual bandit (e.g. LinUCB or a small neural bandit):
- Is more sample-efficient — matters because real operator feedback
  volume will be sparse, especially early on.
- Updates incrementally without target networks, discounted returns, or
  experience-replay complexity.
- Is easier to defend in the report/viva: simpler math, and arguably the
  *more* sophisticated engineering choice for this specific problem,
  not a weaker one.

### Technical design

**Context (state) per incoming event — what the bandit observes:**
- Detection confidence score
- Event type (`ppe_violation` / `zone_intrusion`)
- Zone/camera identity
- Time-of-day / shift
- Recent false-positive rate for that specific zone/camera

**Action (what it controls):**
- `escalate` (send urgent alert)
- `log_only` (record, don't alert)
- `adjust_threshold` (raise/lower the confidence threshold for that
  zone/camera going forward)

**Reward (the learning signal) — human-in-the-loop, not synthetic:**
- Comes from the dashboard's Confirm/False-Alarm buttons (Person D
  builds the UI; you consume the resulting Operator Feedback events per
  INTERFACES.md).
- Confirmed leads to positive reward. False alarm leads to negative
  reward. A retroactively-identified missed event would carry a strong
  negative reward (if your dashboard supports marking missed events at
  all — coordinate scope with D).

**Training approach — this is the safety-critical part, follow it
exactly, don't improvise a simpler version:**
1. **Never train live from scratch with random exploration** — a bad
   early policy could suppress a real safety alert.
2. Log events + feedback to a DB table (coordinate schema with Person D)
   as `(context, action, reward)` tuples.
3. Run **incremental updates only** — on a schedule (e.g. every few
   hours or every N new feedback events), starting from the *current*
   weights, using only the *new* batch since the last update. Never a
   full retrain from scratch — that's slow and defeats the point of
   "self-maintaining."
4. **Validate before deploying, every time** — test the updated policy
   against a held-out set of past confirmed/false-alarm events. Only
   deploy if it beats the currently-live policy's performance on that
   held-out set.
5. **Version every policy** (`policy_v1`, `policy_v2`, ...) and keep the
   previous version retrievable — a bad update must be instantly
   rollback-able, never silently pushed to production.
6. **Training happens on the cloud only** — edge devices run inference
   only (the already-trained policy), never train. Keeps Jetson Nano
   fast and lightweight.

**Output format (matches INTERFACES.md's Bandit Decision Output):**
```json
{
  "event_id": "evt_98213",
  "action": "escalate",
  "policy_version": "policy_v7",
  "threshold_used": 0.75
}
```

### Federated piece (your model, Person D's infrastructure)
Your bandit's weights are what gets federated — each site trains its own
bandit locally on its own feedback, and only the **weight updates**
(never raw feedback, never video) get sent to Person D's Flower server
for FedAvg aggregation into a shared global policy. Coordinate the
exact weight-serialization format with D early, since that's the
literal payload crossing the federated boundary.

### Explicitly out of scope for this module
- Full DQN implementation (rejected, see reasoning above)
- Continuous/online training without the validation gate
- Any training happening on the edge device

---

## Person D — Backend, Dashboard, and Federation

### What this module does
The glue holding the whole system together: receives events from A and
B, hosts the human-feedback loop that C depends on for learning, and
runs the federated layer that lets multiple sites improve a shared
policy without sharing raw data.

### 1. FastAPI backend (`cloud/backend/`)

**Endpoints needed:**
- `POST /events` — receives Detection Events from both A's and B's
  `infer.py` scripts (they already POST here once you give them a URL —
  A's script has an `--api-url` flag ready to point at you).
- `POST /feedback` — receives Operator Feedback from the dashboard
  (Confirm/False-Alarm clicks) — this is literally Person C's reward
  signal, so the exact field names here need direct sign-off from C
  before you finalize the endpoint.
- `GET /alerts` — dashboard polls this for the current/recent alert
  feed (post-bandit-decision, i.e., what actually got escalated).
- Internal: whatever endpoint/mechanism C's decision layer uses to pull
  new events and push back its Bandit Decision Output — coordinate
  directly with C on whether this is a shared DB table, an internal
  API call, or a queue — don't assume, ask.

**DB schema (coordinate with C on exact needs):**
- Events table (raw detection events from A/B)
- Feedback table (operator clicks, timestamped, linked to event_id)
- Policy versions table (matches the Policy Update Record schema —
  `policy_version`, `trained_at`, `validation_score`,
  `previous_version`, `deployed`)

### 2. Dashboard (`dashboard/`)

**Core requirement (this is not optional — the whole self-maintaining
pitch depends on this working):**
- Live alert feed showing events after they've passed through C's
  bandit decision (i.e., the ones marked `escalate`, not raw
  unfiltered detections).
- **Confirm / False Alarm buttons on each alert** — this is the
  human-in-the-loop mechanism. Every click here becomes a training
  signal for Person C's bandit. This needs to work reliably before
  anything else in the dashboard is polished.

**Nice-to-have, if time allows:**
- Zone editor (visual polygon drawing for Person B's zone configs) —
  otherwise B can hand-edit JSON, which is completely fine for a
  capstone demo.
- Historical view of policy versions / validation scores over time
  (nice evidence for the report, not required for the demo to work).

### 3. Federated layer (`cloud/federated/`, Flower + FedAvg)

- Each simulated "site" runs its own local incremental bandit update
  (Person C's training code) independently and frequently.
- **Periodically (weekly — deliberately less frequent than local
  updates), each site sends ONLY its updated bandit policy weights** to
  a central Flower server. Never raw events, never feedback logs, never
  video — this is the actual privacy story, don't let it leak.
- FedAvg aggregates weights from all sites into one improved global
  policy.
- Global policy redistributed back to every site (replaces or merges
  with each site's local policy — simplest for capstone scope: global
  replaces local, since per-site feedback volume will likely be low and
  benefits more from pooling than from preserving local specialization).

**Demo approach:** simulate 2-3 "sites" as separate script
instances/terminals (can be on the same machine or different laptops on
the same network) — this is standard, expected practice for demonstrating
federated learning in a student project. State this plainly as
"simulated multi-site deployment" in the report; even published FL
papers commonly simulate clients.

### 4. Privacy: face-blurring — needs an owner, decide with A/B

Someone needs to implement: detect faces in any captured clip (YuNet or
RetinaFace-nano — both fast enough for edge use) and blur them **before**
the clip is stored or leaves the device. This logically sits at the
edge-capture step (inside A's or B's clip-capture code, whichever module
triggers the capture), not in your backend — but you're the one who
needs the *blurred-only* guarantee to hold for your storage/training
pipeline, so make sure this is explicitly assigned to someone and not
assumed to "just happen." Note in the report: this is "best-effort
automated anonymization," not a 100% guarantee (face detectors miss
some angles/occlusions) — an honest limitation, not a bug.

### Explicitly out of scope for this module
- Do not build the bandit's actual learning algorithm — that's Person
  C's model. You provide the infrastructure (DB, endpoints, federation
  plumbing) that it runs inside.
- Do not implement PPE or zone detection logic — you consume events
  from A/B, you don't generate them.

---

## Cross-team coordination checklist (do this before writing more code)

- [ ] C and D agree on the exact Operator Feedback field names/types
      (dashboard to bandit reward signal)
- [ ] C and D agree on how the bandit reads new events and writes back
      its Decision Output (shared DB table? internal API call?)
- [ ] A, B, and D agree on who owns the face-blurring utility so it
      isn't built twice, differently, by two people
- [ ] B confirms with A whether Person A's `DebounceTracker` class is
      generic enough to import/reuse directly, or needs to be
      reimplemented for B's zone-intrusion use case
- [ ] Everyone confirms their module's tests run with zero GPU/camera/
      real-model dependency, per CONTRIBUTING.md's CI requirement

# Design Decisions Log

Every material design decision goes here, dated, with a one-line reason. This
is your paper trail for the report and viva — don't skip entries just because
the decision felt obvious at the time; it won't feel obvious to an examiner
asking "why not X" six weeks from now.

Format:
```
## YYYY-MM-DD — Short title
Decided: <the decision>
Why: <the reasoning>
```

---

## 2026-09-05 — Scope: drop hospital patient safety module
Decided: focus entirely on industrial safety (PPE + restricted-zone
intrusion), drop hospital fall-detection module.
Why: keeps scope tighter and achievable in the timeline; restricted-zone
logic is domain-agnostic so no capability is lost.

## 2026-09-05 — One unified system, not separate modules
Decided: PPE detection and zone intrusion are two detection capabilities
feeding one decision layer, not two separate products.
Why: matches the actual product story — one safety system with two "senses."

## 2026-09-05 — Contextual bandit instead of DQN for decision layer
Decided: use a contextual bandit (e.g., LinUCB / neural bandit) instead of
DQN for the self-maintaining alert decision layer.
Why: alert decisions (escalate/log/adjust-threshold) are single-step, not
sequential — a bandit is more sample-efficient with sparse operator feedback,
and far cheaper to update incrementally than a DQN.

## 2026-09-05 — Cloud-side incremental retraining, not edge, not full retrain
Decided: bandit training happens only on the cloud, incrementally (new batch
+ existing weights), never fully from scratch, and never on the edge device.
Why: keeps Jetson Nano fast/lightweight (inference only); incremental update
is cheap enough to run frequently; full retrains would be wasteful and slow.

## 2026-09-05 — Validation gate before deploying any updated policy
Decided: every retrained policy is tested against a held-out set of past
confirmed/false-alarm events before going live; versioned for rollback.
Why: safety-critical system — a degraded policy must never silently reach
production.

## 2026-09-05 — Face-blurring at the edge before any cloud upload
Decided: detect and blur faces on-device immediately after capture; only
blurred clips are ever sent to the cloud or used for training.
Why: none of the models need facial identity to learn (PPE presence, zone
position, motion pattern only); this gives a genuine privacy-preserving story
without hurting training quality. Framed as "best-effort automated
anonymization" since face detectors aren't 100% reliable at all angles.

## 2026-09-05 — 10-second clip window for temporal anomaly model
Decided: capture 5s before + 5s after a flagged event for I3D/Video Swin
training data, trigger-based only (not continuous recording).
Why: a single frame can't show lingering/erratic behavior — the entire point
of a temporal model requires a clip window; trigger-based capture keeps
storage bounded.

## 2026-09-05 — Demo uses staged/simulated footage and simulated multi-site federation
Decided: demo with self-recorded staged footage (real detection, real
Jetson Nano) rather than a real industrial deployment; federation demoed
across 2-3 simulated "sites" (separate cameras/instances).
Why: no realistic access to an actual factory for a capstone timeline; this
is standard practice for student FL projects and will be stated explicitly
as a limitation/future-work item in the report.

## 2026-09-07 — PPE final model choice: v4 over v5
Decided: select ppe_yolov11n_v4 checkpoint (ppe_final_v4.pt) as production model for Module A.
Why: v4 achieves higher aggregate mAP50 (0.7366 vs 0.7218) and mAP50-95 (0.4949 vs 0.4793) with higher precision (0.8816 vs 0.7775). While experimental v5 attempted to improve no_goggles, it caused unacceptable regressions in no_gloves and no_mask.

## 2026-09-07 — PPE dataset limitations: no_boots and no_goggles data scarcity
Decided: accept no_boots (mAP50 ≈ 0.0–0.03) and no_goggles (mAP50 ≈ 0.16–0.53) performance as documented data-scarcity limitations without further hyperparameter tuning.
Why: count_classes analysis confirms no_boots has only 108 train instances (38 images, 721 total across all 4 datasets) compared to 5,000–11,500+ for well-performing classes (e.g. no_helmet: 11,511 train; no_mask: 8,571 train; no_vest: 6,898 train). no_goggles is similarly data-limited (2,968 train instances) and designated secondary priority.
## 2026-09-10 — Dual-mode exploration architecture for decision layer
Decided: support both LinUCB and Thompson Sampling (plus epsilon-greedy baseline)
behind a strategy flag in ContextualBandit.
Why: LinUCB provides deterministic, step-by-step scoring ideal for live viva
demo explainability, while Thompson Sampling provides superior sample efficiency
under sparse operator feedback. Epsilon-greedy is retained as a baseline for
comparative benchmarking in the report.

## 2026-09-10 — Safety-first graded reward matrix
Decided: use a cost-sensitive graded reward matrix where log_only on a confirmed
violation carries the heaviest penalty (-2.0).
Why: missed safety violations present direct physical risk to workers and
represent the worst possible real-world failure mode, requiring a far steeper
penalty than operator alert fatigue from false escalations (-1.0).

## 2026-09-10 — Immediate threshold adjustment at prediction time
Decided: threshold adjustment reacts to raw detection confidence at prediction time
rather than waiting for operator feedback confirmation.
Why: trades responsiveness for simplicity within the capstone timeline; a
feedback-gated threshold update is noted as future work.



## 2026-09-22 — Real Module C integration completed in cloud/backend/adapter.py
Decided: replace MockBanditAdapter with RealBanditAdapter in cloud/backend/adapter.py.
Why: MockBanditAdapter used hardcoded threshold logic that never called the real
ContextualBandit. RealBanditAdapter wraps cloud/decision_layer/bandit.py directly,
calling .predict() for decisions and .update() for online feedback. It warm-starts
from the same seed dataset as train_baseline.py (policy_v0 → policy_v1, val ≥ 0.60).
MockBanditAdapter is retained in the file for isolated unit-test use only.
Key mapping: Pydantic stores JSON "class" as .class_name; _to_bandit_dict() remaps
it back to "class" before calling bandit.extract_features().

## 2026-09-23 — Final integration verification pass
Decided: confirm all modules genuinely wired end-to-end; fix two integration bugs found.
Why: pre-presentation verification required — not just "files exist" but live HTTP evidence.
Bugs fixed: (1) flower_client.py error-handler referenced `args.site-id` (hyphen, Python
subtraction) instead of `args.site_id` (underscore); only triggered when gRPC fails, benign
if server is up first. (2) dashboard/app.js simulateEvent() sent `class: "person_in_restricted_area"`
for zone_intrusion events — does not match INTERFACES.md; corrected to `"person_in_zone"`.
Federation note: flwr.server.start_server() and flwr.client.start_numpy_client() emit
DEPRECATED FEATURE warnings in the installed Flower version. Both still function correctly
for the 2-round demo. Recommend upgrading to flower-superlink/flower-supernode CLI before
the next major milestone, but not a blocker for the capstone presentation.

## 2026-09-22 — Real A/b matrix serialisation in cloud/federated/adapter.py
Decided: upgrade PolicyWeightAdapter to serialise the full ContextualBandit A/b
precision matrices (3 actions × (256 + 16) = 816 float64 values across 6 arrays)
instead of the previous 5-element placeholder threshold vector.
Why: the 5-element vector was a proxy that did not capture actual learned policy
state, so FedAvg was averaging meaningless numbers. The real A/b matrices ARE the
policy. Legacy dict_to_weights / weights_to_dict helpers are retained for the
flower_client.py local-adaptation step which uses a simpler threshold-dict format.
Privacy guarantee is unchanged: only numeric weight values cross site boundaries.

# Demo Backup Plan

## Record a screen-capture run before presentation day

**Do this the evening before your presentation:**

1. Do a full dry-run of `demo/run_demo.md` from start to finish.
2. Record your screen the entire time. On Windows:
   - **Xbox Game Bar** (built-in): `Win + G` → Record button, or `Win + Alt + R`
   - **OBS Studio** (free): better quality, captures multiple windows
3. Save the recording to your desktop or a USB drive — somewhere accessible
   in under 10 seconds.

## What to show if live execution breaks

If anything in the live demo fails and you cannot fix it in ~30 seconds:

1. **Immediately say:** "Let me show you the recording from our rehearsal."
   Don't debug live in front of the professor — switch to the recording.
2. Play the recording. It proves the system works. A recording of a working
   demo is better than a broken live demo.

## What to pre-record as separate clips (recommended)

Record each major step as its own short clip (~60–90 seconds) so you can jump
directly to the relevant step if only part of the live demo breaks:

| Clip | What it shows |
|---|---|
| `clip_01_backend_start.mp4` | `uvicorn` starting, `/health` returning 200 |
| `clip_02_ppe_detection.mp4` | `infer.py` on a demo image, event appearing in `/alerts` |
| `clip_03_zone_intrusion.mp4` | Zone pipeline firing, event appearing in dashboard |
| `clip_04_dashboard_feedback.mp4` | Dashboard feed loading, clicking Confirm and False Alarm |
| `clip_05_federation.mp4` | flower_server + 2 clients, "Run finished 2 round(s)" message |

## USB drive checklist (bring this to the presentation room)

- [ ] The repo (with virtual environment intact)
- [ ] Model weights: `edge/ppe_detection/models/ppe_final_v4.pt`
- [ ] Full screen-capture recording
- [ ] Individual step clips (optional but recommended)
- [ ] This `demo/` folder with all demo images and the run script
- [ ] A note with all passwords/wifi credentials if you need network access

## If the model weights file is missing on the presentation laptop

The `.pt` weights file is excluded from git (`.gitignore`). Copy it manually
onto the presentation machine before the demo:
```
edge\ppe_detection\models\ppe_final_v4.pt   (16.0 MB)
```

Without this file, Module A (`infer.py`) will fail immediately with
`FileNotFoundError`. Confirm it exists before you present:
```
dir edge\ppe_detection\models\ppe_final_v4.pt
```

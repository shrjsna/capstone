# Demo Videos — ACTION REQUIRED before presentation

## Zone Intrusion Video

No zone-intrusion video clip exists in the repo test fixtures. The repo contains
`edge/zone_intrusion/events.jsonl` with logged events from previous runs, but the
source video is not committed (too large for git, excluded by `.gitignore`).

**You must add a video before your presentation.**

### What to get

A short royalty-free clip (5–30 seconds) showing a person walking into a clearly
visible zone — ideally an industrial or warehouse setting where the zone polygon
makes visual sense. Suggested sources:
- **Pexels**: https://www.pexels.com/search/videos/walking/
- **Pixabay**: https://pixabay.com/videos/search/person%20walking/

### Exact filename to use

Save it as:
```
demo/videos/zone_intrusion_demo.mp4
```

This is the filename referenced in `demo/run_demo.md`. Do not rename it.

### Requirements

- Format: MP4 (H.264)
- Duration: 5–30 seconds (shorter = faster demo)
- Resolution: any (the YOLO model handles arbitrary sizes)
- Content: at least one person visibly crossing into the frame from outside
  the zone boundary (x=750–1050 pixels per `zones/camera_01_zones.json`)

### Testing it before presentation day

After placing the file, run:
```
python -m edge.zone_intrusion.tracking.zone_intrusion_pipeline \
    --source demo/videos/zone_intrusion_demo.mp4 \
    --zone_config edge/zone_intrusion/zones/camera_01_zones.json \
    --debounce_frames 4 \
    --events_log demo/zone_intrusion_events.jsonl
```

Confirm an event fires and appears in `demo/zone_intrusion_events.jsonl`.

### If you cannot source a video before the presentation

Use the dashboard's **"+ Zone Intrusion"** button to inject a synthetic event
directly. It calls `POST /events` with the correct schema. The bandit will make
a real decision. This is equivalent for demonstrating the backend/bandit loop
even without a real video feed.

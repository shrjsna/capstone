# Module B: Zone Intrusion Detection

Part of the **Edge-Cloud Collaborative AI System for Real-Time Video Analytics**.
Module B detects when people enter restricted zones, using YOLOv11n person detection +
ByteTrack tracking + polygon zone-check + consecutive-frame debounce.

---

## Supported Input Sources

`cv2.VideoCapture` transparently accepts any of these — no code change needed:

| Source type | `--source` value | Example |
|---|---|---|
| Laptop webcam | Integer index | `--source 0` |
| Second USB camera | Integer index | `--source 1` |
| Local video file | File path | `--source demo/videos/zone_intrusion_demo.mp4` |
| RTSP/CCTV camera | RTSP URL | `--source rtsp://192.168.1.50:554/stream1` |
| IP webcam app (MJPEG) | HTTP URL | `--source http://192.168.1.10:8080/video` |

---

## Running the Pipeline

```bash
# From repo root — webcam
python -m edge.zone_intrusion.tracking.zone_intrusion_pipeline \
    --source 0 \
    --zone_config edge/zone_intrusion/zones/camera_01_zones.json \
    --debounce_frames 4 \
    --events_log edge/zone_intrusion/events.jsonl \
    --api-url http://127.0.0.1:8000/events

# From repo root — local video file
python -m edge.zone_intrusion.tracking.zone_intrusion_pipeline \
    --source demo/videos/zone_intrusion_demo.mp4 \
    --zone_config edge/zone_intrusion/zones/camera_01_zones.json \
    --debounce_frames 4 \
    --events_log edge/zone_intrusion/events.jsonl \
    --api-url http://127.0.0.1:8000/events

# From repo root — RTSP IP/CCTV camera
python -m edge.zone_intrusion.tracking.zone_intrusion_pipeline \
    --source rtsp://192.168.1.50:554/stream1 \
    --zone_config edge/zone_intrusion/zones/camera_01_zones.json \
    --debounce_frames 4 \
    --events_log edge/zone_intrusion/events.jsonl \
    --api-url http://127.0.0.1:8000/events

# Phone as IP camera (using e.g. "IP Webcam" Android app on port 8080)
python -m edge.zone_intrusion.tracking.zone_intrusion_pipeline \
    --source http://192.168.1.25:8080/video \
    --zone_config edge/zone_intrusion/zones/camera_01_zones.json \
    --debounce_frames 4 \
    --events_log edge/zone_intrusion/events.jsonl \
    --api-url http://127.0.0.1:8000/events
```

### CLI Arguments

| Argument | Default | Description |
|---|---|---|
| `--source` | (required) | Video source: index, file path, RTSP URL, or HTTP URL |
| `--model` | `yolo11n.pt` | YOLO model weights path |
| `--zone_config` | `../zones/camera_01_zones.json` | Path to zone polygon JSON config |
| `--debounce_frames` | `4` | Consecutive in-zone frames required before firing an event |
| `--events_log` | `../events.jsonl` | JSONL file to append fired events to |
| `--clips_dir` | `../clips` | Directory to save 10-second blurred clips into |
| `--source_fps` | `15.0` | Source FPS hint for rolling clip buffer sizing |
| `--api-url` | `None` | Backend endpoint to POST events to (e.g. `http://127.0.0.1:8000/events`) |
| `--camera-id` | (zone config value) | Override the camera_id field in emitted events |

---

## Zone Config Format

Zone configs live in `zones/` and follow the format expected by `zone_check.py`:

```json
{
  "camera_id": "cam_01",
  "zone_id": "zone_red_1",
  "polygon": [
    [750, 0],
    [1050, 0],
    [1050, 1000],
    [750, 1000]
  ]
}
```

- `polygon`: list of `[x, y]` pixel coordinates forming a closed polygon
- Zone configs can also be created via the AEGIS Dashboard → **Detection & Live Stream** panel → **Draw Zone** tab

---

## Phone as Camera Source

**Method 1 — Phone's own browser:**
Open the AEGIS dashboard on the phone's browser at `http://<laptop-ip>:8080`, grant camera permission, and use the "Webcam Snapshot" detection mode. The phone's camera is used via WebRTC in the browser — no pipeline script needed.

**Method 2 — Phone as IP camera app:**
Install a free "IP Webcam" app on Android (e.g. [IP Webcam by Pavel Khlebovich](https://play.google.com/store/apps/details?id=com.pas.webcam)) or equivalent on iOS. Start the server in the app, note the URL shown (e.g. `http://192.168.1.25:8080/video` for MJPEG). Use that URL as `--source`.

---

## Common Errors

**`cv2.error: (-215:Assertion failed) !_src.empty()`** — source opened but produced no frames. Usually means the RTSP URL is wrong or the stream isn't yet broadcasting. Verify the URL in VLC first.

**`ConnectionRefusedError` when posting events** — backend isn't running. Start `uvicorn cloud.backend.main:app --host 0.0.0.0 --port 8000` first.

**Zone polygon appears off-screen** — polygon coordinates are calibrated for a specific resolution. If your camera resolution differs from the original calibration, the zone will appear at unexpected pixel positions. Recalibrate using the dashboard's Draw Zone tool or `draw_zone.py`.

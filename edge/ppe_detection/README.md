# Module A: Real-Time PPE Compliance Detection

Part of the **Edge-Cloud Collaborative AI System for Real-Time Video Analytics**. Module A performs real-time edge detection and tracking of personal protective equipment (PPE) compliance across camera feeds, emitting debounced events conforming strictly to the shared system interface contract (`INTERFACES.md`).

---

## 1. Overview & Capabilities

Module A provides:
- **Unified 16-Class PPE Detection**: Detects worker presence and compliance across 6 core safety categories:
  - `helmet` / `no_helmet`
  - `vest` / `no_vest`
  - `gloves` / `no_gloves`
  - `boots` / `no_boots`
  - `goggles` / `no_goggles`
  - `mask` / `no_mask`
  - Context & site objects: `person`, `safety_cone`, `machinery`, `vehicle`
- **Multi-Object Tracking**: ByteTrack integration to track worker entities across video frames.
- **Consecutive-Frame Debounce**: Configurable threshold filtering (default: 3 consecutive frames) to prevent transient false alerts and repeat alert spam.
- **Contract-Compliant Event Emission**: Generates standard JSON detection events written to local JSONL logs and optionally forwarded to the backend decision layer (`/events`).

---

## 2. Model Checkpoint

The final production model checkpoint is located at:
```
edge/ppe_detection/models/ppe_final_v4.pt
```

### Model Selection: v4 over v5
During experimental fine-tuning of YOLOv11n on the merged 16-class dataset:
- **Run v4 (Selected Final)**:
  - Precision: **0.8816**
  - Recall: **0.6733**
  - mAP50: **0.7366**
  - mAP50-95: **0.4949**
- **Run v5 (Experimental)**:
  - Precision: **0.7775**
  - Recall: **0.6739**
  - mAP50: **0.7218**
  - mAP50-95: **0.4793**

**Decision**: Run **v4** was selected as the final production model. While v5 attempted to improve `no_goggles` detection, it introduced aggregate performance regressions in precision, overall mAP50/mAP50-95, and specifically degraded `no_gloves` and `no_mask` performance.

---

## 3. Known, Accepted Limitations

These are documented research findings regarding training data scarcity, not software defects:

1. **`no_boots` mAP50 ≈ 0.0–0.03**:
   - Only **108 training instances** (in 38 images) and **721 total instances** across all 4 combined source datasets, compared to **5,000–11,000+** instances for well-performing classes (`no_helmet`: 11,511 train / 15,399 total; `no_mask`: 8,571 train / 11,523 total; `no_vest`: 6,898 train / 8,316 total; `no_gloves`: 5,177 train / 7,435 total).
   - This severe class imbalance and data scarcity is an accepted constraint for this phase.
2. **`no_goggles` mAP50 ≈ 0.16–0.53**:
   - Dependent on training run conditions; data-limited (2,968 train / 4,503 total instances), secondary monitoring priority.

---

## 4. Pipeline Execution & Usage

### A. Dataset Preparation (`prepare_dataset.py`)
Merges four raw PPE datasets into the unified 16-class YOLO structure:
```bash
python edge/ppe_detection/data/prepare_dataset.py \
    --dataset1 "data/raw/construction-safety-nvqbd" \
    --dataset2 "data/raw/construction-ppe" \
    --dataset3 "data/raw/My First Project.v1i.yolov11" \
    --dataset4 "data/raw/keremberke-ppe" \
    --out data/merged
```

To verify class instance distributions across splits:
```bash
python edge/ppe_detection/data/count_classes.py --data edge/ppe_detection/data/merged
```

### B. Training (`train.py`)
Fine-tunes YOLOv11n on the merged dataset:
```bash
python edge/ppe_detection/train.py \
    --data data/merged/data.yaml \
    --name ppe_yolov11n \
    --epochs 120 \
    --batch 16
```

If training is interrupted, resume seamlessly from the last checkpoint:
```bash
python edge/ppe_detection/train.py --resume --name ppe_yolov11n
```

### C. Inference & Event Generation (`infer.py`)

Run on live webcam (camera index 0):
```bash
python edge/ppe_detection/infer.py \
    --model edge/ppe_detection/models/ppe_final_v4.pt \
    --source 0
```

Run on a recorded video file with custom debounce and cloud forwarding:
```bash
python edge/ppe_detection/infer.py \
    --model edge/ppe_detection/models/ppe_final_v4.pt \
    --source path/to/video.mp4 \
    --camera-id cam_01 \
    --zone-id zone_A \
    --conf 0.25 \
    --debounce 3 \
    --output-log events_log.jsonl \
    --api-url http://localhost:8000/events
```

CLI Parameters:
- `--model`: Path to model weights (default: `edge/ppe_detection/models/ppe_final_v4.pt`)
- `--source`: Camera index (`0`) or video file path (default: `0`)
- `--camera-id`: Camera identifier string (default: `cam_01`)
- `--zone-id`: Monitoring zone identifier (default: `zone_A`)
- `--conf`: Detection confidence threshold (default: `0.25`)
- `--debounce`: Consecutive confirmation frames required to emit alert (default: `3`)
- `--output-log`: File path for JSONL event logging (default: `events_log.jsonl`)
- `--api-url`: Optional HTTP backend endpoint to POST events to
- `--show`: Display real-time window with bounding boxes
- `--save-video`: Optional path to save annotated output video

---

## 5. Event Output Schema

All events emitted to `events_log.jsonl` and `--api-url` conform to `INTERFACES.md`:

```json
{
  "camera_id": "cam_01",
  "zone_id": "zone_A",
  "event_type": "ppe_violation",
  "class": "no_helmet",
  "confidence": 0.8732,
  "tracked_id": "person_142",
  "timestamp": "2026-09-07T12:00:00Z",
  "frame_count_triggered": 3,
  "clip_captured": false
}
```

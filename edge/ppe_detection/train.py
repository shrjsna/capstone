"""
train.py

Fine-tunes YOLOv11n on the merged PPE dataset (16 classes: helmet/no_helmet,
vest/no_vest, gloves/no_gloves, boots/no_boots, goggles/no_goggles,
mask/no_mask, person, safety_cone, machinery, vehicle).

Usage:
    python train.py --data data/merged/data.yaml --name ppe_yolov11n_v5

If training crashes partway through (e.g. a late-run CUDA OOM), resume it
from the last saved checkpoint instead of starting over:
    python train.py --resume --name ppe_yolov11n_v5

Requires: pip install ultralytics (already installed)
Runs on GPU automatically if available (confirmed working: RTX 5050, CUDA 12.8).
"""

import argparse
from pathlib import Path
from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/merged/data.yaml", help="Path to merged data.yaml")
    parser.add_argument("--epochs", type=int, default=120, help="Training epochs")
    parser.add_argument("--imgsz", type=int, default=640, help="Training image size")
    parser.add_argument("--batch", type=int, default=16, help="Batch size (lower if you hit out-of-memory on 8GB GPU)")
    parser.add_argument("--patience", type=int, default=25, help="Early stopping patience (epochs with no val improvement)")
    parser.add_argument("--name", default="ppe_yolov11n", help="Run name, used for output folder under runs/detect/")
    parser.add_argument("--workers", type=int, default=8, help="Dataloader worker processes (lower to 2-4 if you hit memory/worker-crash errors on Windows)")
    parser.add_argument("--resume", action="store_true",
                         help="Resume a crashed/interrupted run with the same --name from its last checkpoint, "
                              "instead of starting a fresh run. All other args (data/epochs/batch/etc.) are "
                              "ignored when resuming — Ultralytics reuses the original run's saved settings.")
    args = parser.parse_args()

    if args.resume:
        last_ckpt = Path("runs") / "detect" / args.name / "weights" / "last.pt"
        if not last_ckpt.exists():
            raise FileNotFoundError(
                f"No checkpoint found at {last_ckpt} — can't resume. "
                f"Check --name matches the crashed run's folder under runs/detect/."
            )
        print(f"Resuming from checkpoint: {last_ckpt}")
        model = YOLO(str(last_ckpt))
        results = model.train(resume=True)
    else:
        # Load a pretrained YOLOv11n checkpoint (COCO-pretrained) — this is the
        # transfer-learning starting point, not training from scratch.
        model = YOLO("yolo11n.pt")

        # Fine-tune on the merged PPE dataset.
        # device=0 uses your GPU (CUDA:0, confirmed as RTX 5050 via `yolo checks`).
        # Ultralytics auto-manages mosaic/flip/HSV augmentation — no extra config needed.
        results = model.train(
            data=args.data,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            patience=args.patience,
            device=0,
            name=args.name,
            workers=args.workers,
            # Small-dataset-friendly settings:
            cos_lr=True,          # cosine LR schedule — smoother convergence on fewer images
            val=True,             # run validation every epoch so patience/early-stopping works
            plots=True,           # saves confusion matrix, PR curve, etc. to runs/detect/<name>/
            save=True,            # saves best.pt and last.pt checkpoints
        )

    print("\nTraining complete.")
    print("Best weights saved to: runs/detect/{}/weights/best.pt".format(args.name))
    print("Run 'yolo val model=runs/detect/{}/weights/best.pt data={}' to re-check validation metrics.".format(
        args.name, args.data
    ))


if __name__ == "__main__":
    main()

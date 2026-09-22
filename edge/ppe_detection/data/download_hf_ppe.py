"""
download_hf_ppe.py

Downloads the keremberke/protective-equipment-detection dataset from
Hugging Face and writes it to disk in the same Roboflow-style YOLO folder
structure as your other three raw datasets, so prepare_dataset.py can
merge it in as dataset4.

Output structure (matches dataset1/dataset3 layout):
    <out>/train/images/*.jpg   <out>/train/labels/*.txt
    <out>/valid/images/*.jpg   <out>/valid/labels/*.txt
    <out>/test/images/*.jpg    <out>/test/labels/*.txt

Usage:
    pip install datasets pillow
    python download_hf_ppe.py --out "data/raw/keremberke-ppe"

Original dataset classes (index order, per the dataset card):
    0 glove, 1 goggles, 2 helmet, 3 mask, 4 no_glove, 5 no_goggles,
    6 no_helmet, 7 no_mask, 8 no_shoes, 9 shoes
"""

import argparse
from pathlib import Path

from datasets import load_dataset

# HF split name -> our unified split folder name
SPLIT_MAP = {"train": "train", "valid": "valid", "test": "test"}


def convert_split(ds_split, split_name: str, out_root: Path):
    images_dir = out_root / split_name / "images"
    labels_dir = out_root / split_name / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for i, example in enumerate(ds_split):
        image = example["image"]  # PIL Image
        width, height = image.size
        objects = example["objects"]

        stem = f"{split_name}_{i:06d}"
        image_path = images_dir / f"{stem}.jpg"
        label_path = labels_dir / f"{stem}.txt"

        # Convert PIL image to RGB (some datasets store as different modes) and save
        image.convert("RGB").save(image_path, "JPEG")

        lines = []
        bboxes = objects.get("bbox", [])
        categories = objects.get("category", [])
        for bbox, category_id in zip(bboxes, categories):
            # COCO-style bbox: [x_min, y_min, box_width, box_height] in pixels
            x_min, y_min, box_w, box_h = bbox
            x_center = (x_min + box_w / 2) / width
            y_center = (y_min + box_h / 2) / height
            norm_w = box_w / width
            norm_h = box_h / height
            lines.append(f"{category_id} {x_center:.6f} {y_center:.6f} {norm_w:.6f} {norm_h:.6f}")

        label_path.write_text("\n".join(lines) + ("\n" if lines else ""))
        count += 1

    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="Output root folder (goes under your data/raw/)")
    args = parser.parse_args()

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    print("Downloading dataset from Hugging Face (this may take a few minutes, ~1-2GB)...")
    # This dataset ships an old-style loading script that recent `datasets`
    # versions refuse to execute, and its auto-generated parquet mirror
    # collapses config names, so we list and load the parquet files by path
    # directly instead of relying on load_dataset()'s config detection.
    from huggingface_hub import list_repo_files

    repo_id = "keremberke/protective-equipment-detection"
    revision = "refs/convert/parquet"
    all_files = list_repo_files(repo_id, repo_type="dataset", revision=revision)
    parquet_files = [f for f in all_files if f.endswith(".parquet") and f.startswith("full/")]

    if not parquet_files:
        # Fall back to whatever parquet files exist, regardless of prefix
        parquet_files = [f for f in all_files if f.endswith(".parquet")]

    print("Found parquet files:", parquet_files)

    def base_url(path: str) -> str:
        return f"https://huggingface.co/datasets/{repo_id}/resolve/{revision}/{path}"

    data_files = {}
    for f in parquet_files:
        lower = f.lower()
        if "train" in lower:
            data_files.setdefault("train", []).append(base_url(f))
        elif "valid" in lower:
            data_files.setdefault("valid", []).append(base_url(f))
        elif "test" in lower:
            data_files.setdefault("test", []).append(base_url(f))

    if not data_files:
        raise RuntimeError(
            f"Could not find train/valid/test parquet files under the expected paths. "
            f"All files found at this revision: {all_files}"
        )

    ds = load_dataset("parquet", data_files=data_files)

    totals = {}
    for hf_split, out_split in SPLIT_MAP.items():
        if hf_split not in ds:
            print(f"  Skipping '{hf_split}' — not present in dataset.")
            continue
        print(f"Converting split '{hf_split}' -> '{out_split}'...")
        n = convert_split(ds[hf_split], out_split, out_root)
        totals[out_split] = n
        print(f"  -> {n} images written")

    print("\nDone. Dataset written to:", out_root.resolve())
    print("Totals:", totals)
    print("\nNext: add this as --dataset4 in prepare_dataset.py (see DATASET4_MAP).")


if __name__ == "__main__":
    main()

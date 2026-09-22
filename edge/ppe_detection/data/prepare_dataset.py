"""
prepare_dataset.py

Merges four PPE datasets into one unified YOLO-format dataset with a single
consistent class list:
  1. Roboflow "construction-safety-nvqbd"
  2. Ultralytics "construction-ppe"
  3. Roboflow "My First Project" by pk (adds no_glove / boots / glasses volume)
  4. keremberke/protective-equipment-detection via Hugging Face
     (run download_hf_ppe.py first — adds no_goggles / no_boots volume)

Usage:
    python prepare_dataset.py \
        --dataset1 "data/raw/construction-safety-nvqbd" \
        --dataset2 "data/raw/construction-ppe" \
        --dataset3 "data/raw/My First Project.v1i.yolov11" \
        --dataset4 "data/raw/keremberke-ppe" \
        --out data/merged

(Windows paths with spaces: keep the quotes around the argument.)

Expected input structure:
    dataset1/{train,valid,test}/{images,labels}/...
    dataset2/images/{train,val,test}/... and dataset2/labels/{train,val,test}/...
    dataset3/{train,valid,test}/{images,labels}/...
    (Ultralytics format sometimes ships images/ and labels/ as siblings,
    not nested per-split — this script handles both by locating labels next
    to images by filename.)

Output structure:
    out/{train,valid,test}/images/...
    out/{train,valid,test}/labels/...
    out/data.yaml
"""

import argparse
import shutil
from pathlib import Path

# --- Unified class list (index is the FINAL class id used for training) ---
UNIFIED_CLASSES = [
    "helmet",        # 0
    "no_helmet",     # 1
    "vest",          # 2
    "no_vest",       # 3
    "gloves",        # 4
    "no_gloves",     # 5
    "boots",         # 6
    "no_boots",      # 7
    "goggles",       # 8
    "no_goggles",    # 9
    "mask",          # 10
    "no_mask",       # 11
    "person",        # 12
    "safety_cone",   # 13
    "machinery",     # 14
    "vehicle",       # 15
]
CLASS_TO_ID = {name: i for i, name in enumerate(UNIFIED_CLASSES)}

# --- Dataset 1 (Roboflow construction-safety-nvqbd) old_id -> unified class name ---
DATASET1_MAP = {
    0: "helmet",       # Hardhat
    1: "mask",         # Mask
    2: "no_helmet",    # NO-Hardhat
    3: "no_mask",      # NO-Mask
    4: "no_vest",      # NO-Safety Vest
    5: "person",       # Person
    6: "safety_cone",  # Safety Cone
    7: "vest",         # Safety Vest
    8: "machinery",    # machinery
    9: "vehicle",      # vehicle
}

# --- Dataset 2 (Ultralytics construction-ppe) old_id -> unified class name ---
# old_id 5 ("none") is intentionally omitted -> boxes with this class are dropped
DATASET2_MAP = {
    0: "helmet",
    1: "gloves",
    2: "vest",
    3: "boots",
    4: "goggles",
    # 5: "none"  -- dropped, ambiguous catch-all
    6: "person",
    7: "no_helmet",
    8: "no_goggles",
    9: "no_gloves",
    10: "no_boots",
}

# --- Dataset 3 ("My First Project" by pk, 21 classes incl. case-variant dupes) ---
# old_id -> unified class name. Case-variant duplicates (Hardhat/hardhat,
# Mask/mask, Safety Vest/safety_vest, NO-Hardhat/no_hardhat, NO-Mask/no_mask,
# Person/person) map to the same unified class, as does glasses->goggles and
# shoes->boots (footwear).
DATASET3_MAP = {
    0: "helmet",       # Hardhat
    1: "mask",         # Mask
    2: "no_helmet",    # NO-Hardhat
    3: "no_mask",      # NO-Mask
    4: "no_vest",      # NO-Safety Vest
    5: "person",       # Person
    6: "safety_cone",  # Safety Cone
    7: "vest",         # Safety Vest
    8: "boots",        # boots
    9: "goggles",      # glasses
    10: "gloves",      # glove
    11: "helmet",      # hardhat (lowercase dupe)
    12: "machinery",   # machinery
    13: "mask",        # mask (lowercase dupe)
    14: "no_gloves",   # no_glove
    15: "no_helmet",   # no_hardhat (lowercase dupe)
    16: "no_mask",     # no_mask (lowercase dupe)
    17: "person",      # person (lowercase dupe)
    18: "vest",        # safety_vest (lowercase dupe)
    19: "boots",       # shoes (footwear -> boots)
    20: "vehicle",     # vehicle
}

# --- Dataset 4 (keremberke/protective-equipment-detection via HF, converted
# by download_hf_ppe.py) old_id -> unified class name. Index order per the
# dataset card: 0 glove, 1 goggles, 2 helmet, 3 mask, 4 no_glove,
# 5 no_goggles, 6 no_helmet, 7 no_mask, 8 no_shoes, 9 shoes
DATASET4_MAP = {
    0: "gloves",
    1: "goggles",
    2: "helmet",
    3: "mask",
    4: "no_gloves",
    5: "no_goggles",
    6: "no_helmet",
    7: "no_mask",
    8: "no_boots",   # no_shoes -> no_boots
    9: "boots",      # shoes -> boots
}

# Roboflow split names -> unified split names
SPLIT_NAMES_OUT = ["train", "valid", "test"]


def remap_label_line(line: str, old_to_name: dict) -> str | None:
    """Remap a single YOLO label line. Returns remapped line or None if dropped."""
    line = line.strip()
    if not line:
        return None
    parts = line.split()
    old_id = int(parts[0])
    if old_id not in old_to_name:
        return None
    new_id = CLASS_TO_ID[old_to_name[old_id]]
    return " ".join([str(new_id)] + parts[1:])


def remap_label_file(src_label_path: Path, dst_label_path: Path, old_to_name: dict):
    """Read a YOLO .txt label file, remap class ids, write to destination.
    Lines whose old class id isn't in old_to_name (e.g. dataset2's 'none') are dropped."""
    if not src_label_path.exists():
        # image with no objects — still fine, just write an empty label file
        dst_label_path.write_text("")
        return

    out_lines = []
    for line in src_label_path.read_text().strip().splitlines():
        remapped = remap_label_line(line, old_to_name)
        if remapped is not None:
            out_lines.append(remapped)

    dst_label_path.write_text("\n".join(out_lines) + ("\n" if out_lines else ""))


def copy_split(images_dir: Path, labels_dir: Path, out_split_dir: Path, old_to_name: dict,
                only_if_contains_old_ids: set = None):
    """Copy all images in images_dir + remapped labels into out_split_dir.
    If only_if_contains_old_ids is given, an image is copied only if at least
    one of its label lines has an old class id in that set — used to pull in
    just the images that actually help a specific weak class, rather than
    the whole dataset."""
    out_images = out_split_dir / "images"
    out_labels = out_split_dir / "labels"
    out_images.mkdir(parents=True, exist_ok=True)
    out_labels.mkdir(parents=True, exist_ok=True)

    if not images_dir.exists():
        return 0

    count = 0
    for img_path in images_dir.iterdir():
        if img_path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        label_path = labels_dir / (img_path.stem + ".txt")

        if only_if_contains_old_ids is not None:
            if not label_path.exists():
                continue
            old_ids_in_image = {
                int(line.split()[0])
                for line in label_path.read_text().strip().splitlines()
                if line.strip()
            }
            if old_ids_in_image.isdisjoint(only_if_contains_old_ids):
                continue  # this image has none of the classes we want — skip it

        dst_img = out_images / img_path.name
        dst_label = out_labels / (img_path.stem + ".txt")

        # avoid filename collisions between source datasets
        if dst_img.exists():
            dst_img = out_images / f"{img_path.stem}_dup{img_path.suffix}"
            dst_label = out_labels / f"{img_path.stem}_dup.txt"

        shutil.copy2(img_path, dst_img)
        remap_label_file(label_path, dst_label, old_to_name)
        count += 1
    return count


def merge_dataset1(root: Path, out: Path):
    """Roboflow layout: root/{train,valid,test}/{images,labels}"""
    totals = {}
    for split in SPLIT_NAMES_OUT:
        images_dir = root / split / "images"
        labels_dir = root / split / "labels"
        n = copy_split(images_dir, labels_dir, out / split, DATASET1_MAP)
        totals[split] = n
    return totals


def merge_dataset3(root: Path, out: Path):
    """Roboflow layout: root/{train,valid,test}/{images,labels}"""
    totals = {}
    for split in SPLIT_NAMES_OUT:
        images_dir = root / split / "images"
        labels_dir = root / split / "labels"
        n = copy_split(images_dir, labels_dir, out / split, DATASET3_MAP)
        totals[split] = n
    return totals


def merge_dataset4(root: Path, out: Path, filter_to_weak_classes: bool = True):
    """Same layout as download_hf_ppe.py writes: root/{train,valid,test}/{images,labels}
    By default, only pulls in images containing no_goggles (old id 5) or
    no_shoes/no_boots (old id 8) — the two classes this dataset was added
    for — rather than the whole ~12k-image dataset, since the other classes
    are already well-covered by datasets 1-3. Pass filter_to_weak_classes=False
    to bring in everything instead."""
    totals = {}
    weak_old_ids = {5, 8} if filter_to_weak_classes else None  # no_goggles, no_shoes
    for split in SPLIT_NAMES_OUT:
        images_dir = root / split / "images"
        labels_dir = root / split / "labels"
        n = copy_split(images_dir, labels_dir, out / split, DATASET4_MAP,
                        only_if_contains_old_ids=weak_old_ids)
        totals[split] = n
    return totals


def merge_dataset2(root: Path, out: Path):
    """Ultralytics layout: root/images/{train,val,test}, root/labels/{train,val,test}"""
    split_map = {"train": "train", "valid": "val", "test": "test"}
    totals = {}
    for out_split, src_split in split_map.items():
        images_dir = root / "images" / src_split
        labels_dir = root / "labels" / src_split
        n = copy_split(images_dir, labels_dir, out / out_split, DATASET2_MAP)
        totals[out_split] = n
    return totals


def write_data_yaml(out: Path):
    lines = [
        f"train: {(out / 'train' / 'images').resolve()}",
        f"val: {(out / 'valid' / 'images').resolve()}",
        f"test: {(out / 'test' / 'images').resolve()}",
        "",
        f"nc: {len(UNIFIED_CLASSES)}",
        f"names: {UNIFIED_CLASSES}",
        "",
    ]
    (out / "data.yaml").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset1", required=True, help="Path to Roboflow construction-safety-nvqbd root")
    parser.add_argument("--dataset2", required=True, help="Path to Ultralytics construction-ppe root")
    parser.add_argument("--dataset3", default=None, help="Path to 'My First Project' (pk) root — optional")
    parser.add_argument("--dataset4", default=None, help="Path to converted keremberke HF dataset root — optional")
    parser.add_argument("--out", required=True, help="Output path for merged dataset")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print("Merging dataset 1 (Roboflow)...")
    t1 = merge_dataset1(Path(args.dataset1), out)
    print(f"  -> {t1}")

    print("Merging dataset 2 (Ultralytics)...")
    t2 = merge_dataset2(Path(args.dataset2), out)
    print(f"  -> {t2}")

    t3 = {}
    if args.dataset3:
        print("Merging dataset 3 (pk - My First Project)...")
        t3 = merge_dataset3(Path(args.dataset3), out)
        print(f"  -> {t3}")

    t4 = {}
    if args.dataset4:
        print("Merging dataset 4 (keremberke HF PPE)...")
        t4 = merge_dataset4(Path(args.dataset4), out)
        print(f"  -> {t4}")

    write_data_yaml(out)

    print("\nDone. Merged dataset written to:", out.resolve())
    print("Unified classes:", UNIFIED_CLASSES)
    for split in SPLIT_NAMES_OUT:
        total = t1.get(split, 0) + t2.get(split, 0) + t3.get(split, 0) + t4.get(split, 0)
        print(f"  {split}: {total} images")


if __name__ == "__main__":
    main()

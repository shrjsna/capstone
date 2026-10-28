"""
count_classes.py

Counts how many labeled instances of each class exist in each split
(train/valid/test) of the merged dataset. Use this to see the TRUE class
distribution, since a small validation set can under- or over-represent
a class relative to what the model actually trained on.

Usage:
    python count_classes.py --data data/merged
"""

import argparse
from pathlib import Path
from collections import defaultdict

UNIFIED_CLASSES = [
    "helmet", "no_helmet", "vest", "no_vest", "gloves", "no_gloves",
    "boots", "no_boots", "goggles", "no_goggles", "mask", "no_mask",
    "person", "safety_cone", "machinery", "vehicle",
]


def count_split(labels_dir: Path):
    counts = defaultdict(int)
    images_with_class = defaultdict(set)
    if not labels_dir.exists():
        return counts, images_with_class

    for label_file in labels_dir.glob("*.txt"):
        seen_classes_this_image = set()
        for line in label_file.read_text().strip().splitlines():
            if not line.strip():
                continue
            class_id = int(line.split()[0])
            counts[class_id] += 1
            seen_classes_this_image.add(class_id)
        for c in seen_classes_this_image:
            images_with_class[c].add(label_file.stem)

    return counts, images_with_class


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Path to merged dataset root (contains train/valid/test)")
    args = parser.parse_args()

    root = Path(args.data)
    splits = ["train", "valid", "test"]

    all_counts = {}
    all_images = {}
    for split in splits:
        labels_dir = root / split / "labels"
        counts, images = count_split(labels_dir)
        all_counts[split] = counts
        all_images[split] = images

    # Print a table: class name | train instances (images) | valid | test | TOTAL
    header = f"{'Class':<15} {'Train (imgs)':<16} {'Valid (imgs)':<16} {'Test (imgs)':<16} {'Total instances':<16}"
    print(header)
    print("-" * len(header))
    for class_id, class_name in enumerate(UNIFIED_CLASSES):
        row = [class_name]
        total = 0
        for split in splits:
            n_instances = all_counts[split].get(class_id, 0)
            n_images = len(all_images[split].get(class_id, set()))
            total += n_instances
            row.append(f"{n_instances} ({n_images})")
        print(f"{row[0]:<15} {row[1]:<16} {row[2]:<16} {row[3]:<16} {total:<16}")

    print("\nFormat: instance_count (image_count) — how many boxes vs how many distinct images contain that class.")
    print("A class with few TRAIN instances will likely stay weak regardless of validation set size.")


if __name__ == "__main__":
    main()

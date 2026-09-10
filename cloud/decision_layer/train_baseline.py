"""
Offline Baseline Policy Trainer
===============================
Trains initial baseline policy_v1 for ContextualBandit using seed synthetic historical events.
Produces a Policy Update Record matching INTERFACES.md.
"""

import json
import os
import sys

# Ensure root capstone directory is on python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from cloud.decision_layer.bandit import ContextualBandit


def generate_seed_dataset():
    """
    Generate synthetic seed historical dataset for baseline offline training.

    Includes 20 training examples and 8 validation examples across:
    - Event types: ppe_violation, zone_intrusion
    - Classes: no_helmet, no_vest, no_gloves, person_in_zone
    - Mix of high-confidence violations, low-confidence noise, and marginal cases.
    """
    training_batch = [
        # --- High-Confidence Violations (escalate -> confirmed) ---
        ({"event_type": "ppe_violation", "class": "no_helmet", "confidence": 0.91, "frame_count_triggered": 6}, "escalate", "confirmed"),
        ({"event_type": "ppe_violation", "class": "no_vest", "confidence": 0.88, "frame_count_triggered": 5}, "escalate", "confirmed"),
        ({"event_type": "ppe_violation", "class": "no_gloves", "confidence": 0.86, "frame_count_triggered": 4}, "escalate", "confirmed"),
        ({"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.95, "frame_count_triggered": 8}, "escalate", "confirmed"),
        ({"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.92, "frame_count_triggered": 7}, "escalate", "confirmed"),
        ({"event_type": "ppe_violation", "class": "no_helmet", "confidence": 0.94, "frame_count_triggered": 9}, "escalate", "confirmed"),
        ({"event_type": "ppe_violation", "class": "no_vest", "confidence": 0.87, "frame_count_triggered": 5}, "escalate", "confirmed"),
        ({"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.89, "frame_count_triggered": 6}, "escalate", "confirmed"),

        # --- Low-Confidence Noise (log_only -> false_alarm) ---
        ({"event_type": "ppe_violation", "class": "no_gloves", "confidence": 0.35, "frame_count_triggered": 2}, "log_only", "false_alarm"),
        ({"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.28, "frame_count_triggered": 1}, "log_only", "false_alarm"),
        ({"event_type": "ppe_violation", "class": "no_vest", "confidence": 0.40, "frame_count_triggered": 2}, "log_only", "false_alarm"),
        ({"event_type": "ppe_violation", "class": "no_helmet", "confidence": 0.32, "frame_count_triggered": 1}, "log_only", "false_alarm"),
        ({"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.44, "frame_count_triggered": 2}, "log_only", "false_alarm"),
        ({"event_type": "ppe_violation", "class": "no_gloves", "confidence": 0.30, "frame_count_triggered": 2}, "log_only", "false_alarm"),

        # --- Marginal / Borderline Cases (adjust_threshold -> confirmed / false_alarm) ---
        ({"event_type": "ppe_violation", "class": "no_vest", "confidence": 0.74, "frame_count_triggered": 3}, "adjust_threshold", "confirmed"),
        ({"event_type": "ppe_violation", "class": "no_helmet", "confidence": 0.76, "frame_count_triggered": 4}, "adjust_threshold", "confirmed"),
        ({"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.72, "frame_count_triggered": 3}, "adjust_threshold", "confirmed"),
        ({"event_type": "ppe_violation", "class": "no_gloves", "confidence": 0.71, "frame_count_triggered": 3}, "adjust_threshold", "false_alarm"),
        ({"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.77, "frame_count_triggered": 4}, "adjust_threshold", "confirmed"),
        ({"event_type": "ppe_violation", "class": "no_vest", "confidence": 0.69, "frame_count_triggered": 3}, "adjust_threshold", "false_alarm"),
    ]

    validation_set = [
        ({"event_type": "ppe_violation", "class": "no_helmet", "confidence": 0.90, "frame_count_triggered": 6}, "escalate", "confirmed"),
        ({"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.94, "frame_count_triggered": 7}, "escalate", "confirmed"),
        ({"event_type": "ppe_violation", "class": "no_vest", "confidence": 0.87, "frame_count_triggered": 5}, "escalate", "confirmed"),
        ({"event_type": "ppe_violation", "class": "no_gloves", "confidence": 0.85, "frame_count_triggered": 4}, "escalate", "confirmed"),
        ({"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.33, "frame_count_triggered": 2}, "log_only", "false_alarm"),
        ({"event_type": "ppe_violation", "class": "no_gloves", "confidence": 0.38, "frame_count_triggered": 2}, "log_only", "false_alarm"),
        ({"event_type": "ppe_violation", "class": "no_vest", "confidence": 0.75, "frame_count_triggered": 3}, "adjust_threshold", "confirmed"),
        ({"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.73, "frame_count_triggered": 3}, "adjust_threshold", "confirmed"),
    ]

    return training_batch, validation_set


def train_offline_baseline():
    # Initialize bandit at policy_v0
    bandit = ContextualBandit(strategy="linucb", policy_version="policy_v0")
    training_batch, validation_set = generate_seed_dataset()

    # Train baseline policy
    record = bandit.retrain(
        training_batch=training_batch,
        validation_set=validation_set,
        min_validation_score=0.60
    )

    print("=== Offline Baseline Policy Training Complete ===")
    print(f"Training Batch Size: {len(training_batch)} examples")
    print(f"Validation Set Size: {len(validation_set)} examples")
    print(json.dumps(record, indent=2))
    return record


if __name__ == "__main__":
    train_offline_baseline()

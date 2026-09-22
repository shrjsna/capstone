"""
cloud/backend/adapter.py
BanditAdapter interface, MockBanditAdapter (kept for reference), and
RealBanditAdapter which wraps the real ContextualBandit from Module C.

Integration status: RealBanditAdapter is active as of 2026-09-22.
See docs/decisions.md for the dated decision entry.
"""

from abc import ABC, abstractmethod
from typing import Dict
from cloud.backend.schemas import DetectionEventCreate, BanditDecisionOutput, OperatorFeedbackCreate
from cloud.decision_layer.bandit import ContextualBandit


class BanditAdapter(ABC):
    """Abstract interface defining the decision layer contract required by Module D."""

    @abstractmethod
    def decide(self, event: DetectionEventCreate, event_id: str) -> BanditDecisionOutput:
        """Evaluates a detection event and returns an action decision."""
        pass

    @abstractmethod
    def submit_feedback(self, feedback: OperatorFeedbackCreate) -> None:
        """Forwards human operator feedback to the decision layer to update policy rewards."""
        pass

    @abstractmethod
    def get_zone_thresholds(self) -> Dict[str, float]:
        """Returns current per-zone sensitivity thresholds."""
        pass


class RealBanditAdapter(BanditAdapter):
    """
    Production adapter wrapping the real ContextualBandit from Module C
    (cloud/decision_layer/bandit.py).

    Interface mapping:
    - decide()           → bandit.predict(event_dict, event_id) -> BanditDecisionOutput
    - submit_feedback()  → bandit.update(event_id, feedback_str)
    - get_zone_thresholds() → derived from bandit.thresholds registry

    The bandit is pre-warmed with the offline baseline policy (policy_v1) at
    construction time using the same seed dataset as train_baseline.py, so it
    starts with a real trained state rather than a cold identity matrix.
    """

    def __init__(self):
        self.bandit = ContextualBandit(strategy="linucb", policy_version="policy_v1")
        self._warm_start()

    def _warm_start(self) -> None:
        """
        Apply the same offline baseline training as train_baseline.py so the
        adapter starts with a real trained policy, not cold identity matrices.
        Mirrors cloud/decision_layer/train_baseline.py:generate_seed_dataset().
        """
        training_batch = [
            ({"event_type": "ppe_violation", "class": "no_helmet", "confidence": 0.91, "frame_count_triggered": 6}, "escalate", "confirmed"),
            ({"event_type": "ppe_violation", "class": "no_vest", "confidence": 0.88, "frame_count_triggered": 5}, "escalate", "confirmed"),
            ({"event_type": "ppe_violation", "class": "no_gloves", "confidence": 0.86, "frame_count_triggered": 4}, "escalate", "confirmed"),
            ({"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.95, "frame_count_triggered": 8}, "escalate", "confirmed"),
            ({"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.92, "frame_count_triggered": 7}, "escalate", "confirmed"),
            ({"event_type": "ppe_violation", "class": "no_helmet", "confidence": 0.94, "frame_count_triggered": 9}, "escalate", "confirmed"),
            ({"event_type": "ppe_violation", "class": "no_vest", "confidence": 0.87, "frame_count_triggered": 5}, "escalate", "confirmed"),
            ({"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.89, "frame_count_triggered": 6}, "escalate", "confirmed"),
            ({"event_type": "ppe_violation", "class": "no_gloves", "confidence": 0.35, "frame_count_triggered": 2}, "log_only", "false_alarm"),
            ({"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.28, "frame_count_triggered": 1}, "log_only", "false_alarm"),
            ({"event_type": "ppe_violation", "class": "no_vest", "confidence": 0.40, "frame_count_triggered": 2}, "log_only", "false_alarm"),
            ({"event_type": "ppe_violation", "class": "no_helmet", "confidence": 0.32, "frame_count_triggered": 1}, "log_only", "false_alarm"),
            ({"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.44, "frame_count_triggered": 2}, "log_only", "false_alarm"),
            ({"event_type": "ppe_violation", "class": "no_gloves", "confidence": 0.30, "frame_count_triggered": 2}, "log_only", "false_alarm"),
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
        self.bandit.retrain(
            training_batch=training_batch,
            validation_set=validation_set,
            min_validation_score=0.60,
        )

    def _event_to_dict(self, event: DetectionEventCreate) -> Dict:
        """
        Convert Pydantic DetectionEventCreate to the plain dict the bandit expects.
        Key remapping: Pydantic stores 'class' as 'class_name' internally (due to
        Python keyword clash) but bandit.extract_features() reads the 'class' key.
        """
        return {
            "camera_id": event.camera_id,
            "zone_id": event.zone_id,
            "event_type": event.event_type,
            "class": event.class_name,        # Pydantic alias: stored as class_name, bandit reads "class"
            "confidence": event.confidence,
            "tracked_id": event.tracked_id,
            "timestamp": event.timestamp,
            "frame_count_triggered": event.frame_count_triggered,
            "clip_captured": event.clip_captured,
        }

    def decide(self, event: DetectionEventCreate, event_id: str) -> BanditDecisionOutput:
        """Pass event through the real ContextualBandit and return decision."""
        event_dict = self._event_to_dict(event)
        decision = self.bandit.predict(event_dict, event_id=event_id)
        return BanditDecisionOutput(
            event_id=decision["event_id"],
            action=decision["action"],
            policy_version=decision["policy_version"],
            threshold_used=decision["threshold_used"],
        )

    def submit_feedback(self, feedback: OperatorFeedbackCreate) -> None:
        """Forward operator feedback to the real bandit's online update step."""
        self.bandit.update(feedback.event_id, feedback.feedback)

    def get_zone_thresholds(self) -> Dict[str, float]:
        """
        Return the bandit's current per-camera/zone threshold registry.
        Keys in bandit.thresholds are "camera_id:zone_id"; we return them as-is
        plus a 'default' fallback from bandit.DEFAULT_THRESHOLD.
        """
        from cloud.decision_layer.bandit import DEFAULT_THRESHOLD
        thresholds = dict(self.bandit.thresholds)
        if "default" not in thresholds:
            thresholds["default"] = DEFAULT_THRESHOLD
        return thresholds


class MockBanditAdapter(BanditAdapter):
    """
    Mock decision adapter with simulated threshold adjustment logic.
    Retained for reference and testing. Not used in production — see get_bandit_adapter().
    """

    def __init__(self):
        self.policy_version = "v1.0.0-mock"
        self.zone_thresholds: Dict[str, float] = {
            "zone_a": 0.70,
            "zone_b": 0.75,
            "default": 0.70,
        }

    def _get_threshold(self, zone_id: str) -> float:
        return self.zone_thresholds.get(zone_id, self.zone_thresholds["default"])

    def decide(self, event: DetectionEventCreate, event_id: str) -> BanditDecisionOutput:
        threshold = self._get_threshold(event.zone_id)
        action = "escalate" if event.confidence >= threshold else "log_only"
        return BanditDecisionOutput(
            event_id=event_id,
            action=action,
            policy_version=self.policy_version,
            threshold_used=threshold
        )

    def submit_feedback(self, feedback: OperatorFeedbackCreate) -> None:
        if feedback.feedback == "confirmed":
            for zone in self.zone_thresholds:
                self.zone_thresholds[zone] = max(0.40, round(self.zone_thresholds[zone] - 0.02, 3))
        elif feedback.feedback == "false_alarm":
            for zone in self.zone_thresholds:
                self.zone_thresholds[zone] = min(0.95, round(self.zone_thresholds[zone] + 0.03, 3))

    def get_zone_thresholds(self) -> Dict[str, float]:
        return self.zone_thresholds.copy()


# ── Active adapter ──────────────────────────────────────────────────────────
# RealBanditAdapter is the live production adapter (wired 2026-09-22).
# To revert to mock for isolated testing, swap to MockBanditAdapter() here.
_bandit_adapter_instance: BanditAdapter = RealBanditAdapter()


def get_bandit_adapter() -> BanditAdapter:
    """Factory function returning the active BanditAdapter instance."""
    return _bandit_adapter_instance

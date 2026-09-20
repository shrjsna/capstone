"""
cloud/backend/adapter.py
BanditAdapter interface and MockBanditAdapter implementation for decision layer isolation.

NOTE: Replace MockBanditAdapter with RealBanditAdapter once Module C integration is ready.
"""

from abc import ABC, abstractmethod
from typing import Dict
from cloud.backend.schemas import DetectionEventCreate, BanditDecisionOutput, OperatorFeedbackCreate


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


class MockBanditAdapter(BanditAdapter):
    """
    Mock decision adapter with simulated threshold adjustment logic.
    TODO: Replace with real Module C integration when available.
    """

    def __init__(self):
        self.policy_version = "v1.0.0-mock"
        # Dynamic per-zone thresholds
        self.zone_thresholds: Dict[str, float] = {
            "zone_a": 0.70,
            "zone_b": 0.75,
            "default": 0.70,
        }

    def _get_threshold(self, zone_id: str) -> float:
        return self.zone_thresholds.get(zone_id, self.zone_thresholds["default"])

    def decide(self, event: DetectionEventCreate, event_id: str) -> BanditDecisionOutput:
        threshold = self._get_threshold(event.zone_id)
        # Simple mock logic: escalate if confidence >= zone threshold, else log_only
        if event.confidence >= threshold:
            action = "escalate"
        else:
            action = "log_only"

        return BanditDecisionOutput(
            event_id=event_id,
            action=action,
            policy_version=self.policy_version,
            threshold_used=threshold
        )

    def submit_feedback(self, feedback: OperatorFeedbackCreate) -> None:
        """
        Mock reward update:
        - Confirmed alert -> Lower threshold slightly (increases sensitivity)
        - False alarm -> Raise threshold slightly (reduces false alerts)
        """
        # We simulate nudging default threshold or specific zones if trackable
        if feedback.feedback == "confirmed":
            for zone in self.zone_thresholds:
                self.zone_thresholds[zone] = max(0.40, round(self.zone_thresholds[zone] - 0.02, 3))
        elif feedback.feedback == "false_alarm":
            for zone in self.zone_thresholds:
                self.zone_thresholds[zone] = min(0.95, round(self.zone_thresholds[zone] + 0.03, 3))

    def get_zone_thresholds(self) -> Dict[str, float]:
        return self.zone_thresholds.copy()


# Singleton instance for mock adapter across requests
_bandit_adapter_instance: BanditAdapter = MockBanditAdapter()


def get_bandit_adapter() -> BanditAdapter:
    """Factory function returning the active BanditAdapter instance."""
    return _bandit_adapter_instance

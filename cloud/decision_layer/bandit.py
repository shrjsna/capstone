"""
Bandit Decision Layer Module
============================
Industrial Safety Monitoring System — PPE violation + zone intrusion detection with adaptive alerting.

Design Note:
------------
As documented in docs/decisions.md (Entry 2026-09-05: "Contextual bandit instead of DQN for decision layer"):
Alert decisions (escalate / log_only / adjust_threshold) are single-step contextual bandit problems,
not sequential multi-step MDPs. Contextual bandits are far more sample-efficient under sparse operator
feedback, fast to update incrementally, and easy to inspect/explain during a project viva or demo.
"""

import math
import datetime
from typing import Dict, List, Tuple, Union, Optional
import numpy as np


# Exact data contract constants per INTERFACES.md
ACTIONS = ["escalate", "log_only", "adjust_threshold"]
DEFAULT_THRESHOLD = 0.75
FEATURE_DIM = 16


class ContextualBandit:
    """
    Contextual Bandit decision module for industrial safety alerting.

    Supports LinUCB (Disjoint Linear Upper Confidence Bound), Linear Thompson Sampling,
    and Epsilon-Greedy exploration strategies over a shared Bayesian ridge precision state.
    Tracks dynamic per-camera/zone detection thresholds adaptively when adjust_threshold fires.
    """

    def __init__(
        self,
        strategy: str = "linucb",
        alpha: float = 0.5,
        v_sq: float = 0.25,
        epsilon: float = 0.1,
        policy_version: str = "policy_v1",
        random_state: Optional[int] = 42,
    ):
        """
        Initialize ContextualBandit instance.

        Args:
            strategy: Exploration strategy ('linucb', 'thompson', 'epsilon_greedy').
            alpha: LinUCB exploration parameter (higher = more exploration).
            v_sq: Variance multiplier for Thompson Sampling posterior sampling.
            epsilon: Exploration probability for epsilon-greedy strategy.
            policy_version: Initial policy version string.
            random_state: Seed for reproducibility.
        """
        if strategy not in ["linucb", "thompson", "epsilon_greedy"]:
            raise ValueError(f"Unknown strategy '{strategy}'. Must be one of: linucb, thompson, epsilon_greedy")

        self.strategy = strategy
        self.alpha = alpha
        self.v_sq = v_sq
        self.epsilon = epsilon
        self.policy_version = policy_version
        self.previous_version = policy_version
        self.rng = np.random.default_rng(random_state)

        # In-memory matrix state per action:
        # A_a: precision matrix (d x d), initialized to Identity I
        # b_a: response vector (d x 1), initialized to zero vector
        self.d = FEATURE_DIM
        self.A = {a: np.eye(self.d, dtype=np.float64) for a in ACTIONS}
        self.b = {a: np.zeros((self.d, 1), dtype=np.float64) for a in ACTIONS}

        # Backup matrix state for rollback support
        self.previous_A = {a: self.A[a].copy() for a in ACTIONS}
        self.previous_b = {a: self.b[a].copy() for a in ACTIONS}

        # Dynamic per-camera/zone threshold registry: key format "camera_id:zone_id" -> float threshold
        self.thresholds: Dict[str, float] = {}

        # In-memory storage mapping event_id -> {"context": x, "action": action, "timestamp": ts}
        self.pending_events: Dict[str, Dict] = {}

    def get_threshold(self, camera_id: str, zone_id: str) -> float:
        """Retrieve current dynamic detection threshold for a given camera and zone."""
        key = f"{camera_id}:{zone_id}"
        return self.thresholds.get(key, DEFAULT_THRESHOLD)

    def extract_features(self, event: Dict) -> np.ndarray:
        """
        Extract numerical feature/context vector x from an incoming detection event.

        Feature breakdown (dim=16):
        - [0]: confidence (float [0.0, 1.0])
        - [1]: threshold_diff (confidence - active_threshold)
        - [2]: confidence_sq (confidence ** 2)
        - [3]: normalized_frame_count (min(frame_count, 30) / 10.0)
        - [4]: clip_captured (1.0 or 0.0)
        - [5..7]: event_type one-hot (ppe_violation, zone_intrusion, unknown)
        - [8..12]: class one-hot (no_helmet, no_vest, no_gloves, person_in_zone, unknown)
        - [13..14]: cyclic time-of-day [sin(2*pi*h/24), cos(2*pi*h/24)]
        - [15]: bias term (1.0)
        """
        if not isinstance(event, dict):
            event = {}

        camera_id = str(event.get("camera_id", "default_cam"))
        zone_id = str(event.get("zone_id", "default_zone"))
        active_thresh = self.get_threshold(camera_id, zone_id)

        # 1. Numeric confidence with fallback
        try:
            confidence = float(event.get("confidence", 0.5))
            if math.isnan(confidence) or math.isinf(confidence):
                confidence = 0.5
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.5

        thresh_diff = confidence - active_thresh
        conf_sq = confidence ** 2

        # 2. Debounce frame count
        try:
            frame_count = float(event.get("frame_count_triggered", 3))
            if math.isnan(frame_count) or math.isinf(frame_count):
                frame_count = 3.0
        except (ValueError, TypeError):
            frame_count = 3.0
        norm_frame_count = min(max(frame_count, 0.0), 30.0) / 10.0

        # 3. Clip captured boolean
        clip_captured = 1.0 if bool(event.get("clip_captured", False)) else 0.0

        # 4. Event type one-hot encoding
        event_type = str(event.get("event_type", "")).lower()
        ev_ppe = 1.0 if event_type == "ppe_violation" else 0.0
        ev_zone = 1.0 if event_type == "zone_intrusion" else 0.0
        ev_other = 1.0 if (ev_ppe == 0.0 and ev_zone == 0.0) else 0.0

        # 5. Class name one-hot encoding
        cls_name = str(event.get("class", "")).lower()
        cls_helmet = 1.0 if cls_name == "no_helmet" else 0.0
        cls_vest = 1.0 if cls_name == "no_vest" else 0.0
        cls_gloves = 1.0 if cls_name == "no_gloves" else 0.0
        cls_zone = 1.0 if cls_name == "person_in_zone" else 0.0
        cls_other = 1.0 if (cls_helmet == 0.0 and cls_vest == 0.0 and cls_gloves == 0.0 and cls_zone == 0.0) else 0.0

        # 6. Time of day cyclic features
        ts_str = str(event.get("timestamp", ""))
        hour = 12.0  # default noon
        if ts_str:
            try:
                clean_ts = ts_str.replace("Z", "+00:00")
                dt = datetime.datetime.fromisoformat(clean_ts)
                hour = float(dt.hour) + float(dt.minute) / 60.0
            except Exception:
                hour = 12.0

        sin_hour = math.sin(2.0 * math.pi * hour / 24.0)
        cos_hour = math.cos(2.0 * math.pi * hour / 24.0)

        # Assemble array
        x = np.array(
            [
                confidence,
                thresh_diff,
                conf_sq,
                norm_frame_count,
                clip_captured,
                ev_ppe,
                ev_zone,
                ev_other,
                cls_helmet,
                cls_vest,
                cls_gloves,
                cls_zone,
                cls_other,
                sin_hour,
                cos_hour,
                1.0,  # Bias term
            ],
            dtype=np.float64,
        ).reshape(self.d, 1)

        return x

    def select_action(self, x: np.ndarray) -> str:
        """
        Select action for context vector x based on the configured strategy.
        Epsilon-greedy performs a single explore/exploit check per prediction call.
        """
        # Epsilon-Greedy Exploration: single random check per prediction round
        if self.strategy == "epsilon_greedy" and self.rng.random() < self.epsilon:
            return str(self.rng.choice(ACTIONS))

        scores = {}

        for a in ACTIONS:
            A_inv = np.linalg.inv(self.A[a])
            theta_hat = A_inv @ self.b[a]

            if self.strategy == "linucb":
                # LinUCB: p_a = theta_hat^T x + alpha * sqrt(x^T A_inv x)
                var = (x.T @ A_inv @ x).item()
                std_dev = math.sqrt(max(0.0, var))
                scores[a] = (theta_hat.T @ x).item() + self.alpha * std_dev

            elif self.strategy == "thompson":
                # Thompson Sampling: sample theta_tilde ~ N(theta_hat, v_sq * A_inv)
                cov = self.v_sq * A_inv
                cov = (cov + cov.T) / 2.0  # Ensure numerical symmetry
                theta_tilde = self.rng.multivariate_normal(theta_hat.flatten(), cov).reshape(self.d, 1)
                scores[a] = (theta_tilde.T @ x).item()

            elif self.strategy == "epsilon_greedy":
                # Epsilon-Greedy Exploitation phase
                scores[a] = (theta_hat.T @ x).item()

        # Pick action with maximum score
        best_action = max(scores, key=scores.get)
        return best_action

    def predict(self, event: Dict, event_id: Optional[str] = None) -> Dict:
        """
        Process a detection event, choose an action, store context in memory,
        dynamically track detection threshold when adjust_threshold fires,
        and return standard Bandit Decision output dictionary per INTERFACES.md.
        """
        if not isinstance(event, dict):
            event = {}

        # Resolve event_id
        if not event_id:
            event_id = str(event.get("event_id", ""))
        if not event_id:
            event_id = f"evt_{abs(hash(str(event))) % 1000000:06d}"

        camera_id = str(event.get("camera_id", "default_cam"))
        zone_id = str(event.get("zone_id", "default_zone"))
        key = f"{camera_id}:{zone_id}"
        current_threshold = self.get_threshold(camera_id, zone_id)

        x = self.extract_features(event)
        action = self.select_action(x)

        # Dynamic Threshold Adaptation Logic
        if action == "adjust_threshold":
            try:
                confidence = float(event.get("confidence", 0.5))
            except (ValueError, TypeError):
                confidence = 0.5

            # Shift threshold adaptively bounded within [0.50, 0.90]
            if confidence > current_threshold:
                new_threshold = min(0.90, current_threshold + 0.02)
            else:
                new_threshold = max(0.50, current_threshold - 0.02)

            threshold_used = round(new_threshold, 4)
            self.thresholds[key] = threshold_used
        else:
            threshold_used = round(current_threshold, 4)

        # Save context & action for later reward lookup in update()
        self.pending_events[event_id] = {
            "context": x,
            "action": action,
            "timestamp": event.get("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat()),
        }

        # Exact schema per INTERFACES.md Section 3
        decision_output = {
            "event_id": event_id,
            "action": action,
            "policy_version": self.policy_version,
            "threshold_used": threshold_used,
        }
        return decision_output

    def calculate_reward(self, action: str, feedback: str) -> float:
        """
        Map operator feedback ('confirmed' / 'false_alarm') to graded reward.

        Safety-First Rebalanced Reward Matrix:
        - log_only + confirmed = -2.0 (CRITICAL: Missed real safety violation, worst risk)
        - escalate + false_alarm = -1.0 (Operator fatigue / unnecessary alarm)
        - escalate + confirmed = +1.0 (True positive alert delivered)
        - log_only + false_alarm = +0.5 (Correct noise suppression)
        - adjust_threshold + confirmed = +0.7 (Appropriate adjustment)
        - adjust_threshold + false_alarm = -0.3 (Mild miscalibration penalty)
        """
        fb = str(feedback).lower()
        is_confirmed = fb == "confirmed"

        if action == "escalate":
            return 1.0 if is_confirmed else -1.0
        elif action == "log_only":
            return -2.0 if is_confirmed else 0.5
        elif action == "adjust_threshold":
            return 0.7 if is_confirmed else -0.3
        else:
            return 0.0

    def update(self, event_id: str, feedback: Union[Dict, str]) -> bool:
        """
        Incrementally update model state based on operator feedback.

        Args:
            event_id: Event ID matching a prior predict() call.
            feedback: Operator feedback dict matching INTERFACES.md schema or raw string ('confirmed'/'false_alarm').

        Returns:
            bool: True if event_id was found and model updated, False if event_id is unrecognized.
        """
        if event_id not in self.pending_events:
            return False

        if isinstance(feedback, dict):
            feedback_str = str(feedback.get("feedback", "false_alarm"))
        else:
            feedback_str = str(feedback)

        record = self.pending_events.pop(event_id)
        x = record["context"]
        action = record["action"]

        r = self.calculate_reward(action, feedback_str)

        # Online Bayesian matrix update:
        # A_a <- A_a + x x^T
        # b_a <- b_a + r * x
        self.A[action] += x @ x.T
        self.b[action] += r * x

        return True

    def retrain(
        self,
        training_batch: List[Tuple[Dict, str, float]],
        validation_set: Optional[List[Tuple[Dict, str, float]]] = None,
        min_validation_score: float = 0.70,
    ) -> Dict:
        """
        Perform batch retraining, run validation gate, and update policy version if passed.

        Args:
            training_batch: List of tuples (event_dict, action_str, reward_float/feedback_str)
            validation_set: Optional held-out validation batch. If None, uses a split of training_batch.
            min_validation_score: Validation gate passing score [0.0, 1.0].

        Returns:
            Dict: Policy Update Record matching INTERFACES.md Section 4.
        """
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if not training_batch:
            return {
                "policy_version": self.policy_version,
                "trained_at": now_iso,
                "validation_score": 0.0,
                "previous_version": self.previous_version,
                "deployed": False,
            }

        # Backup current model state for validation gate & rollback
        candidate_A = {a: self.A[a].copy() for a in ACTIONS}
        candidate_b = {a: self.b[a].copy() for a in ACTIONS}

        # Train candidate weights on training batch
        for item in training_batch:
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            event_dict, action, reward_raw = item[0], item[1], item[2]
            if action not in ACTIONS:
                continue

            x = self.extract_features(event_dict)
            if isinstance(reward_raw, (int, float)):
                r = float(reward_raw)
            else:
                r = self.calculate_reward(action, str(reward_raw))

            candidate_A[action] += x @ x.T
            candidate_b[action] += r * x

        # Prepare validation set
        if not validation_set:
            if len(training_batch) >= 5:
                split_idx = max(1, int(len(training_batch) * 0.8))
                eval_set = training_batch[split_idx:]
            else:
                eval_set = training_batch
        else:
            eval_set = validation_set

        # Evaluate candidate policy on validation set
        positive_evals = 0
        total_eval = 0

        for item in eval_set:
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            event_dict, target_action, reward_raw = item[0], item[1], item[2]
            x = self.extract_features(event_dict)

            # Score action using candidate weights
            scores = {}
            for a in ACTIONS:
                A_inv = np.linalg.inv(candidate_A[a])
                theta_hat = A_inv @ candidate_b[a]
                scores[a] = (theta_hat.T @ x).item()

            pred_action = max(scores, key=scores.get)

            if isinstance(reward_raw, (int, float)):
                r = float(reward_raw)
            else:
                r = self.calculate_reward(pred_action, str(reward_raw))

            total_eval += 1
            if r > 0.0:
                positive_evals += 1

        validation_score = (positive_evals / total_eval) if total_eval > 0 else 0.0

        # Version string bump logic (e.g. policy_v1 -> policy_v2)
        try:
            curr_num = int(self.policy_version.replace("policy_v", ""))
            next_version = f"policy_v{curr_num + 1}"
        except ValueError:
            next_version = f"{self.policy_version}_new"

        # Validation Gate check
        if validation_score >= min_validation_score:
            self.previous_A = {a: self.A[a].copy() for a in ACTIONS}
            self.previous_b = {a: self.b[a].copy() for a in ACTIONS}
            self.previous_version = self.policy_version

            self.A = candidate_A
            self.b = candidate_b
            self.policy_version = next_version
            deployed = True
        else:
            deployed = False

        record = {
            "policy_version": self.policy_version if deployed else next_version,
            "trained_at": now_iso,
            "validation_score": round(validation_score, 4),
            "previous_version": self.previous_version,
            "deployed": deployed,
        }
        return record

    def rollback(self) -> str:
        """Rollback active policy to previous_version."""
        self.A = {a: self.previous_A[a].copy() for a in ACTIONS}
        self.b = {a: self.previous_b[a].copy() for a in ACTIONS}
        self.policy_version = self.previous_version
        return self.policy_version

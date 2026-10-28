# Industrial Safety Decision Layer — Complete Project Guide & Explanation

---

## 1. Project Overview (In Simple Words)

In an industrial workplace (like a factory or construction site), worker safety is critical. Two major safety risks are:
1. **PPE Violations**: Workers not wearing mandatory Personal Protective Equipment (like helmets, safety vests, or gloves).
2. **Restricted Zone Intrusion**: Unauthorized people walking into dangerous hazardous machinery zones.

### What is the Decision Layer?
Instead of having a camera just trigger noisy alarms constantly (which causes "alert fatigue" for safety operators), we built a **Cloud-Based Decision Layer** using **Machine Learning (Reinforcement Learning / Contextual Bandits)**.

When an AI camera detects a potential safety issue:
1. It sends the event details (confidence level, type of risk, time of day, etc.) to our **Decision Layer**.
2. Our **Contextual Bandit AI** decides the best action:
   - 🚨 **`escalate`**: Trigger immediate alarm/notification for serious risks.
   - 📝 **`log_only`**: Quietly record low-confidence background noise without disturbing operators.
   - ⚙️ **`adjust_threshold`**: Dynamically tune camera detection sensitivity up or down.
3. The safety operator gives feedback (**Confirmed Violation** or **False Alarm**).
4. The AI learns immediately from this feedback to get smarter over time.

---

## 2. What We Built (File-by-File Summary)

Here is a breakdown of every file created in the project repository:

| File Path | What It Does | Why It Is Important |
| :--- | :--- | :--- |
| [`cloud/decision_layer/bandit.py`](file:///c:/Users/ROHIT/Desktop/capstone/cloud/decision_layer/bandit.py) | Core Machine Learning engine containing the `ContextualBandit` class. | Handles feature extraction, action selection (`LinUCB`, `Thompson`, `Epsilon-Greedy`), adaptive thresholding, reward matrix, and online matrix updates. |
| [`cloud/decision_layer/train_baseline.py`](file:///c:/Users/ROHIT/Desktop/capstone/cloud/decision_layer/train_baseline.py) | Offline training script that trains the initial policy (`policy_v1`). | Uses a synthetic dataset of 28 safety events to train and validate the initial model baseline before live deployment. |
| [`tests/test_bandit.py`](file:///c:/Users/ROHIT/Desktop/capstone/tests/test_bandit.py) | Unit and integration test suite written with `pytest`. | Ensures every feature (actions, rewards, strategies, edge cases) works reliably without bugs. |
| [`docs/decisions.md`](file:///c:/Users/ROHIT/Desktop/capstone/docs/decisions.md) | Architectural decision record (ADR). | Documents every key engineering choice with dates and explanations for project examination and viva defense. |
| [`conftest.py`](file:///c:/Users/ROHIT/Desktop/capstone/conftest.py) | Pytest configuration file at the repository root. | Fixes Python module import paths so `pytest` can find `cloud.decision_layer` without import errors. |
| [`requirements.txt`](file:///c:/Users/ROHIT/Desktop/capstone/requirements.txt) | Dependency manifest file. | Specifies required Python packages (`numpy`) for clean setup and CI/CD pipelines. |

---

## 3. How the AI Logic Works (Deep Dive in Simple English)

### A. Feature Extraction (16 Numerical Clues)
When a detection happens, `extract_features()` converts the event data into a list of 16 numbers (a feature vector `x`):
1. **Confidence Score**: How sure the camera is (0.0 to 1.0).
2. **Threshold Difference**: How far the confidence is above or below the current active threshold.
3. **Debounce Frame Count**: How many consecutive frames detected the violation.
4. **Clip Captured**: Whether a 10-second video snippet was saved.
5. **Event Type One-Hot**: Is it `ppe_violation` or `zone_intrusion`?
6. **Class Name One-Hot**: Is it `no_helmet`, `no_vest`, `no_gloves`, or `person_in_zone`?
7. **Time of Day (Sin/Cos)**: Helps the model learn day-shift vs night-shift patterns.
8. **Bias Term**: Constant `1.0` for mathematical baseline offset.

### B. Action Selection Strategies

Our system supports **3 distinct strategies** for choosing an action. To understand how they differ, let's use a **Real-World Factory Scenario**:

> 🏭 **Scenario Example**: 
> A camera detects a worker near a dangerous machine appearing to have **no safety vest (`no_vest`)**, but the camera's confidence is **72% (0.72)** (a borderline case).
>
> The AI must pick one of 3 actions:
> 1. `escalate` (Trigger alarm)
> 2. `log_only` (Quiet database log)
> 3. `adjust_threshold` (Lower sensitivity slightly to double-check upcoming frames)

---

#### 1. `Epsilon-Greedy` (Baseline Strategy)
- **How It Works**: Uses a "coin flip" approach based on probability $\epsilon$ (epsilon = 0.1).
  - **90% of the time (Exploitation)**: Plays it safe and picks whatever action has achieved the highest average reward in past data.
  - **10% of the time (Exploration)**: Rolls a 10-sided die and picks a **completely random action** by chance.
- **Scenario Example**:
  - The model calculates historical estimated scores: `escalate = 0.70`, `adjust_threshold = 0.50`, `log_only = 0.20`.
  - **90% Chance**: It automatically picks `escalate` (the top-performing action so far).
  - **10% Chance**: It ignores past scores and picks a random action (e.g., `log_only`), even if `log_only` has historically performed poorly!
- **Why We Use It**: Serves as a standard baseline to compare performance against smarter exploration methods.

---

#### 2. `LinUCB` (Linear Upper Confidence Bound — Recommended for Viva)
- **How It Works**: Calculates **$\text{Total Score} = \text{Estimated Reward} + \text{Uncertainty Bonus}$**.
  - If the AI has seen this exact camera angle and context 500 times, its uncertainty bonus is near **zero** ($+0.05$).
  - If the AI has rarely seen this specific condition (e.g., low light at 72% confidence), its uncertainty bonus is **high** ($+0.45$).
- **Scenario Example**:
  - `escalate`: Estimated Reward = `0.70` + Uncertainty Bonus = `0.10` $\rightarrow$ **Total Score = 0.80**
  - `adjust_threshold`: Estimated Reward = `0.50` + Uncertainty Bonus = `0.45` (High uncertainty because it hasn't tried adjusting threshold much here) $\rightarrow$ **Total Score = 0.95**
  - **Result**: LinUCB selects `adjust_threshold` because **0.95 > 0.80**. It systematically explores the action it knows the least about!
- **Why We Use It**: It is **100% deterministic**. If an examiner during a viva asks *"Why did the AI choose adjust_threshold?"*, you can show the exact mathematical formula: $\text{Score} = \hat{\theta}^T x + \alpha \sqrt{x^T A^{-1} x}$.

---

#### 3. `Thompson Sampling` (Linear Thompson Sampling)
- **How It Works**: Uses Bayesian probability bell curves instead of single fixed numbers.
  - Every action has a bell curve representing the range of possible rewards.
  - The AI takes a **random sample draw** from each action's bell curve and picks whichever sample comes out highest.
- **Scenario Example**:
  - `escalate`: Narrow bell curve centered around `0.75` (high confidence). Random sample drawn: **0.73**.
  - `adjust_threshold`: Wide bell curve centered around `0.60` (uncertain, could be anywhere between 0.30 and 0.95). Random sample drawn: **0.87** (hit a lucky high value on the curve!).
  - **Result**: Thompson Sampling selects `adjust_threshold`. Next time a similar event occurs, it might sample `0.52` and pick `escalate`.
- **Why We Use It**: It naturally explores actions proportional to how likely they are to be optimal. In real-world factory deployments with sparse operator feedback, Thompson Sampling learns faster and adapts smoother than Epsilon-Greedy or LinUCB.

---



### C. Safety-First Graded Reward Matrix
How does the AI know if it did a good job?

| Action Taken | Operator Feedback | Reward Score | Meaning & Reason |
| :--- | :--- | :--- | :--- |
| **`escalate`** | **Confirmed** | **`+1.0`** | ✅ Great job! Real safety violation caught and alerted. |
| **`log_only`** | **Confirmed** | **`-2.0`** | ❌ **CRITICAL FAILURE**: Real safety violation ignored! Heaviest penalty given. |
| **`escalate`** | **False Alarm** | **`-1.0`** | ⚠️ Operator annoyed by false alarm, but worker wasn't in danger. |
| **`log_only`** | **False Alarm** | **`+0.5`** | ✅ Correctly ignored camera noise without disturbing anyone. |
| **`adjust_threshold`** | **Confirmed** | **`+0.7`** | ✅ Successfully adjusted camera sensitivity. |
| **`adjust_threshold`** | **False Alarm** | **`-0.3`** | ⚠️ Mild penalty for minor miscalibration. |

---

## 4. Challenges Faced & How We Solved Them

### ❓ Challenge 1: Missed Safety Violations vs. Operator Alert Fatigue
- **The Problem**: A false alarm (nuisance) annoys the safety manager, but a missed violation (false negative) could cause severe physical injury or death to a worker. Traditional models treat all errors equally.
- **Our Solution**: We engineered an **asymmetric, safety-first reward matrix**. We set the penalty for missing a real violation (`log_only` + `confirmed`) to **`-2.0`**, which is twice as harsh as the penalty for a false alarm (**`-1.0`**). This forces the AI to err on the side of safety.

---

### ❓ Challenge 2: Avoiding Overcomplicated Deep Learning (DQN vs Contextual Bandit)
- **The Problem**: Many AI projects try to use Deep Q-Networks (DQN). However, DQNs require huge amounts of data, heavy GPU resources, slow retraining times, and long temporal sequences.
- **Our Solution**: Alerting decisions are **single-step decisions** (see detection $\rightarrow$ choose action $\rightarrow$ receive reward), not multi-step navigation paths. We chose a **Contextual Bandit**. It updates instantly in memory using fast linear algebra ($A_a \leftarrow A_a + x x^T$), runs smoothly on standard CPUs, and retrains incrementally in seconds.

---

### ❓ Challenge 3: Balancing Viva Demo Explainability with Real Learning Performance
- **The Problem**: Advanced probabilistic models like Thompson Sampling can feel like a "black box" during a project viva examination, making it hard to explain why an action was chosen.
- **Our Solution**: We designed a **Dual-Mode Exploration Architecture**. For project presentations and vivas, we can switch to `LinUCB` mode to explain exact mathematical upper confidence bounds step-by-step. For actual deployment, we can switch to `Thompson Sampling` for superior sample efficiency.

---

### ❓ Challenge 4: Preventing Bad Policy Updates (Model Degradation)
- **The Problem**: If noisy or incorrect operator feedback is fed into the system during retraining, a bad policy update could be deployed to production, breaking safety alerting.
- **Our Solution**: We implemented an automated **Validation Gate** in `retrain()`. Whenever the model retrains:
  1. Candidate weights are evaluated against a held-out validation dataset.
  2. If the validation score is $\ge 0.70$ (the project-standard threshold), the new policy version (e.g., `policy_v2`) is deployed.
  3. If it fails, deployment is rejected, and the system supports an instant 1-click **Rollback** to `previous_version`.

---

### ❓ Challenge 5: Pytest Import Path Errors in Workspace Directory Structure
- **The Problem**: Running `pytest` from the root directory resulted in `ModuleNotFoundError: No module named 'cloud'` because Python did not include the root directory in `sys.path`.
- **Our Solution**: We created a root-level [`conftest.py`](file:///c:/Users/ROHIT/Desktop/capstone/conftest.py) file. This automatically registers the repository root path into Python's module lookup table whenever `pytest` runs, allowing seamless test execution across all subfolders.

---

## 5. How to Run & Verify the Code

### 1. Run Baseline Offline Training
Train the initial baseline model on synthetic safety data:
```bash
python cloud/decision_layer/train_baseline.py
```
*Expected Output*: Output will print a JSON record showing `validation_score: 0.75` and `deployed: true` with `policy_version: policy_v1`.

### 2. Run All Automated Tests
Run the test suite to verify system functionality:
```bash
pytest
```
*Expected Output*: All test cases in `tests/test_bandit.py` will pass cleanly.

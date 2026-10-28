/**
 * SafetyOps Dashboard — JavaScript
 * ===================================
 * Polls the FastAPI backend every 5 seconds, renders the alert feed,
 * handles operator Confirm / False Alarm buttons, retrain, and rollback.
 *
 * Backend base URL — change this if you run on a different port.
 */

const API_BASE = "http://127.0.0.1:8000";

// ─── State ────────────────────────────────────────────────────────────────────
let allAlerts      = [];    // raw array from GET /alerts
let filteredAlerts = [];    // after UI filters applied
let statusFilter   = "all"; // "all" | "pending" | "acknowledged"
let countdownVal   = 5;
let countdownTimer = null;

// ─── Boot ─────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  fetchPolicy();
  fetchAlerts();
  startCountdown();
});

// ─── Auto-refresh countdown ───────────────────────────────────────────────────
function startCountdown() {
  clearInterval(countdownTimer);
  countdownVal = 5;
  updateCountdownUI();
  countdownTimer = setInterval(() => {
    countdownVal--;
    updateCountdownUI();
    if (countdownVal <= 0) {
      countdownVal = 5;
      fetchAlerts();
    }
  }, 1000);
}

function updateCountdownUI() {
  const el = document.getElementById("refresh-countdown");
  if (el) el.textContent = countdownVal;
}

// ─── Fetch policy info ────────────────────────────────────────────────────────
async function fetchPolicy() {
  try {
    const res = await fetch(`${API_BASE}/policy`);
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    document.getElementById("policy-version").textContent = data.policy_version ?? "—";
    document.getElementById("strategy-badge").textContent = (data.strategy ?? "linucb").toUpperCase();
    document.getElementById("feedback-count").textContent = data.feedback_history_size ?? 0;
    document.getElementById("feedback-count-modal").textContent = data.feedback_history_size ?? 0;
  } catch (e) {
    document.getElementById("policy-version").textContent = "offline";
  }
}

// ─── Fetch alerts ─────────────────────────────────────────────────────────────
async function fetchAlerts() {
  startCountdown(); // reset countdown
  try {
    const res = await fetch(`${API_BASE}/alerts?limit=200`);
    if (!res.ok) throw new Error(res.status);
    allAlerts = await res.json();
    updateStats();
    applyFilters();
    fetchPolicy();
  } catch (e) {
    showToast("error", "Connection Error", `Cannot reach backend at ${API_BASE}`);
  }
}

// ─── Stats bar ────────────────────────────────────────────────────────────────
function updateStats() {
  const pending    = allAlerts.filter(a => a.status === "pending").length;
  const acked      = allAlerts.filter(a => a.status === "acknowledged");
  const confirmed  = acked.filter(a => a.feedback === "confirmed").length;
  const falseAlarm = acked.filter(a => a.feedback === "false_alarm").length;
  const precision  = (confirmed + falseAlarm) > 0
    ? Math.round((confirmed / (confirmed + falseAlarm)) * 100) + "%"
    : "—";

  document.getElementById("pending-count").textContent    = pending;
  document.getElementById("confirmed-count").textContent  = confirmed;
  document.getElementById("false-alarm-count").textContent = falseAlarm;
  document.getElementById("accuracy-pct").textContent     = precision;
}

// ─── Filters ──────────────────────────────────────────────────────────────────
function setFilter(val) {
  statusFilter = val;
  document.querySelectorAll(".filter-tab").forEach(t => t.classList.remove("active"));
  document.getElementById(`tab-${val}`).classList.add("active");
  applyFilters();
}

function applyFilters() {
  const typeF   = document.getElementById("type-filter").value;
  const actionF = document.getElementById("action-filter").value;

  filteredAlerts = allAlerts.filter(a => {
    if (statusFilter !== "all" && a.status !== statusFilter) return false;
    if (typeF   !== "all" && a.event_type !== typeF)   return false;
    if (actionF !== "all" && a.action     !== actionF) return false;
    return true;
  });

  renderTable();
}

// ─── Render table ─────────────────────────────────────────────────────────────
function renderTable() {
  const tbody = document.getElementById("alerts-tbody");

  if (filteredAlerts.length === 0) {
    tbody.innerHTML = `
      <tr class="empty-row">
        <td colspan="7">
          <div class="empty-state">
            <div class="empty-icon">📡</div>
            <div class="empty-text">No alerts match the current filter.</div>
            <div class="empty-sub">Waiting for detection events from edge cameras.</div>
          </div>
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = filteredAlerts.map(a => buildRow(a)).join("");
}

function buildRow(a) {
  const isAcked = a.status === "acknowledged";
  const conf    = a.confidence ?? 0;
  const confPct = Math.round(conf * 100);
  const confClass = conf >= 0.75 ? "high" : conf >= 0.55 ? "mid" : "low";
  const actionKey = a.action ?? "log_only";
  const rowClass  = actionKey === "adjust_threshold" ? "adjust" : actionKey;
  const timestamp = a.timestamp
    ? new Date(a.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "—";

  const actionIcons = { escalate: "🚨", log_only: "📝", adjust_threshold: "⚙️" };
  const actionLabels = { escalate: "ESCALATE", log_only: "LOG ONLY", adjust_threshold: "ADJUST" };

  const feedbackBadge = isAcked
    ? `<span class="status-badge status-acknowledged">
        ${a.feedback === "confirmed" ? "✓ Confirmed" : "✗ False Alarm"}
       </span>`
    : `<span class="status-badge status-pending">⏳ Pending</span>`;

  const actionButtons = isAcked
    ? `<span style="font-size:11px;color:var(--text-muted)">by ${a.operator_id ?? "op"}</span>`
    : `<button class="btn btn-confirm" id="confirm-btn-${a.event_id}"
              onclick="submitFeedback('${a.event_id}', 'confirmed')">✓ Confirm</button>
       <button class="btn btn-reject" id="reject-btn-${a.event_id}"
              onclick="submitFeedback('${a.event_id}', 'false_alarm')">✗ False Alarm</button>`;

  return `
    <tr class="row-${rowClass} ${isAcked ? "row-acked" : ""}" id="row-${a.event_id}">
      <td class="time-cell">${timestamp}</td>
      <td class="camera-cell">
        <div class="cam-id">${a.camera_id ?? "—"}</div>
        <div class="zone-id">${a.zone_id ?? "—"}</div>
      </td>
      <td class="violation-cell">
        <div class="ev-type">${(a.event_type ?? "").replace("_", " ")}</div>
        <span class="cls-name">${a.class_name ?? "—"}</span>
      </td>
      <td>
        <div class="conf-bar-wrap">
          <div class="conf-bar">
            <div class="conf-fill ${confClass}" style="width:${confPct}%"></div>
          </div>
          <span class="conf-pct ${confClass}">${confPct}%</span>
        </div>
      </td>
      <td>
        <span class="action-badge action-${actionKey}">
          ${actionIcons[actionKey] ?? "•"} ${actionLabels[actionKey] ?? actionKey}
        </span>
      </td>
      <td>${feedbackBadge}</td>
      <td class="action-cell">${actionButtons}</td>
    </tr>`;
}

// ─── Submit operator feedback ─────────────────────────────────────────────────
async function submitFeedback(eventId, feedback) {
  // Optimistic UI — disable buttons immediately
  const row = document.getElementById(`row-${eventId}`);
  const confirmBtn = document.getElementById(`confirm-btn-${eventId}`);
  const rejectBtn  = document.getElementById(`reject-btn-${eventId}`);
  if (confirmBtn) { confirmBtn.disabled = true; confirmBtn.style.opacity = "0.5"; }
  if (rejectBtn)  { rejectBtn.disabled  = true; rejectBtn.style.opacity  = "0.5"; }

  try {
    const res = await fetch(`${API_BASE}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_id:    eventId,
        feedback:    feedback,
        operator_id: "dashboard_op",
        timestamp:   new Date().toISOString(),
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? res.status);
    }

    const label = feedback === "confirmed" ? "Confirmed" : "False Alarm";
    showToast("success", label + " recorded", `Event ${eventId.slice(-8)} updated. Bandit has learned.`);

    // Refresh immediately
    await fetchAlerts();

  } catch (e) {
    showToast("error", "Feedback failed", String(e.message ?? e));
    if (confirmBtn) { confirmBtn.disabled = false; confirmBtn.style.opacity = "1"; }
    if (rejectBtn)  { rejectBtn.disabled  = false; rejectBtn.style.opacity  = "1"; }
  }
}

// ─── Retrain ──────────────────────────────────────────────────────────────────
document.getElementById("retrain-btn").addEventListener("click", () => {
  document.getElementById("retrain-modal").style.display = "flex";
});

function closeModal(id) {
  document.getElementById(id).style.display = "none";
}

async function doRetrain() {
  closeModal("retrain-modal");
  const gate = parseFloat(document.getElementById("gate-slider").value);
  showToast("info", "Retraining…", `Running validation gate at ${gate.toFixed(2)}`);
  try {
    const res = await fetch(`${API_BASE}/retrain`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ min_validation_score: gate }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail ?? res.status);

    if (data.deployed) {
      showToast("success", "New policy deployed!", `${data.policy_version}  score=${(data.validation_score * 100).toFixed(0)}%`);
    } else {
      showToast("warning", "Gate failed — no deploy", `score=${(data.validation_score * 100).toFixed(0)}% < ${(gate * 100).toFixed(0)}%`);
    }
    fetchPolicy();
  } catch (e) {
    showToast("error", "Retrain failed", String(e.message ?? e));
  }
}

// ─── Rollback ─────────────────────────────────────────────────────────────────
document.getElementById("rollback-btn").addEventListener("click", async () => {
  if (!confirm("Roll back to the previous policy version?")) return;
  try {
    const res = await fetch(`${API_BASE}/rollback`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail ?? res.status);
    showToast("warning", "Rolled back", `Active policy is now ${data.rolled_back_to}`);
    fetchPolicy();
  } catch (e) {
    showToast("error", "Rollback failed", String(e.message ?? e));
  }
});

// ─── Toast notifications ──────────────────────────────────────────────────────
function showToast(type, title, msg, duration = 4000) {
  const icons = { success: "✅", error: "❌", info: "ℹ️", warning: "⚠️" };
  const container = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `
    <div class="toast-icon">${icons[type] ?? "•"}</div>
    <div class="toast-body">
      <div class="toast-title">${title}</div>
      <div class="toast-msg">${msg}</div>
    </div>`;
  container.appendChild(el);
  setTimeout(() => {
    el.style.animation = "toast-in 0.2s ease reverse";
    setTimeout(() => el.remove(), 200);
  }, duration);
}

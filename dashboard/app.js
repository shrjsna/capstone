/**
 * AEGIS Safety Console — JavaScript Application Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  const apiUrlInput = document.getElementById('api-url-input');
  const alertFeedContainer = document.getElementById('alert-feed-container');
  const feedEmptyState = document.getElementById('feed-empty');
  const alertCountBadge = document.getElementById('alert-count-badge');
  const btnRefresh = document.getElementById('btn-refresh');
  const headerPolicyVer = document.getElementById('header-policy-ver');
  
  const thresholdsContainer = document.getElementById('thresholds-container');
  const policyHistoryList = document.getElementById('policy-history-list');

  const btnSimPpe = document.getElementById('btn-sim-ppe');
  const btnSimZone = document.getElementById('btn-sim-zone');

  let currentFilter = 'all';
  let activeAlerts = [];
  let submittedFeedbackMap = new Map(); // Track feedback locally for instant UI update

  function getApiBaseUrl() {
    let url = apiUrlInput.value.trim();
    if (url.endsWith('/')) {
      url = url.slice(0, -1);
    }
    return url;
  }

  // --- Fetch Alerts from Backend ---
  async function fetchAlerts() {
    try {
      const response = await fetch(`${getApiBaseUrl()}/alerts?limit=50`);
      if (!response.ok) throw new Error(`HTTP error ${response.status}`);
      const data = await response.json();
      activeAlerts = data;
      renderAlertFeed();
    } catch (err) {
      console.warn('Failed to fetch alerts:', err.message);
    }
  }

  // --- Fetch Thresholds from Backend ---
  async function fetchThresholds() {
    try {
      const response = await fetch(`${getApiBaseUrl()}/thresholds`);
      if (!response.ok) return;
      const thresholds = await response.json();
      renderThresholds(thresholds);
    } catch (err) {
      console.warn('Failed to fetch thresholds:', err.message);
    }
  }

  // --- Fetch Policy History ---
  async function fetchPolicyHistory() {
    try {
      const response = await fetch(`${getApiBaseUrl()}/policy-history`);
      if (!response.ok) return;
      const history = await response.json();
      if (history.length > 0) {
        headerPolicyVer.textContent = history[0].policy_version;
      }
      renderPolicyHistory(history);
    } catch (err) {
      console.warn('Failed to fetch policy history:', err.message);
    }
  }

  // --- Render Alert Feed ---
  function renderAlertFeed() {
    const filteredAlerts = activeAlerts.filter(alert => {
      if (currentFilter === 'all') return true;
      return alert.event_type === currentFilter;
    });

    alertCountBadge.textContent = `${filteredAlerts.length} Alerts`;

    if (filteredAlerts.length === 0) {
      alertFeedContainer.innerHTML = '';
      alertFeedContainer.appendChild(feedEmptyState);
      feedEmptyState.style.display = 'block';
      return;
    }

    feedEmptyState.style.display = 'none';
    alertFeedContainer.innerHTML = '';

    filteredAlerts.forEach(alert => {
      const card = document.createElement('div');
      card.className = `alert-card ${alert.event_type}`;
      card.id = `alert-${alert.event_id}`;

      const formattedTime = new Date(alert.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      const confPercent = Math.round(alert.confidence * 100);

      const isPpe = alert.event_type === 'ppe_violation';
      const typeLabel = isPpe ? 'PPE Violation' : 'Zone Intrusion';
      const typeClass = isPpe ? 'type-ppe' : 'type-intrusion';
      const actionClass = alert.bandit_action === 'escalate' ? 'action-escalate' : 'action-log';

      const feedbackState = submittedFeedbackMap.get(alert.event_id);

      card.innerHTML = `
        <div class="alert-main-info">
          <div class="alert-tags">
            <span class="tag ${typeClass}">${typeLabel}</span>
            <span class="tag ${actionClass}">${alert.bandit_action ? alert.bandit_action.toUpperCase() : 'LOG'}</span>
            <span class="tag" style="background: rgba(255,255,255,0.06); color: var(--text-muted);">${alert.zone_id}</span>
          </div>
          <div class="alert-title">${alert.class_name.replace('_', ' ').toUpperCase()} Detected (${alert.camera_id})</div>
          <div class="alert-meta">
            <span class="meta-item">Confidence: <strong>${confPercent}%</strong>
              <span class="confidence-bar"><span class="confidence-fill" style="width: ${confPercent}%;"></span></span>
            </span>
            <span class="meta-item">Track ID: <code>${alert.tracked_id}</code></span>
            <span class="meta-item">Time: ${formattedTime}</span>
          </div>
        </div>
        <div class="alert-actions">
          ${feedbackState ? `
            <div class="feedback-status-badge ${feedbackState}">
              ${feedbackState === 'confirmed' ? '✓ CONFIRMED' : '✗ FALSE ALARM'}
            </div>
          ` : `
            <button class="btn-feedback btn-confirm" onclick="submitFeedback('${alert.event_id}', 'confirmed')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
              Confirm
            </button>
            <button class="btn-feedback btn-false-alarm" onclick="submitFeedback('${alert.event_id}', 'false_alarm')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              False Alarm
            </button>
          `}
        </div>
      `;

      alertFeedContainer.appendChild(card);
    });
  }

  // --- Render Threshold Meters ---
  function renderThresholds(thresholds) {
    thresholdsContainer.innerHTML = '';
    for (const [zone, val] of Object.entries(thresholds)) {
      const pct = Math.round(val * 100);
      const card = document.createElement('div');
      card.className = 'threshold-card';
      card.innerHTML = `
        <div class="t-head">
          <span class="t-zone">${zone}</span>
          <span class="t-val">${val.toFixed(2)}</span>
        </div>
        <div class="meter-bar">
          <div class="meter-fill" style="width: ${pct}%;"></div>
        </div>
      `;
      thresholdsContainer.appendChild(card);
    }
  }

  // --- Render Policy History ---
  function renderPolicyHistory(history) {
    policyHistoryList.innerHTML = '';
    history.forEach(item => {
      const el = document.createElement('div');
      el.className = 'history-item';
      const timeStr = new Date(item.trained_at).toLocaleDateString();
      el.innerHTML = `
        <div>
          <strong style="color: var(--accent-cyan);">${item.policy_version}</strong>
          <span style="color: var(--text-dim); margin-left: 6px;">${timeStr}</span>
        </div>
        <div style="font-weight: 600; color: var(--color-confirm);">Score: ${item.validation_score}</div>
      `;
      policyHistoryList.appendChild(el);
    });
  }

  // --- Submit Operator Feedback ---
  window.submitFeedback = async function(eventId, feedbackType) {
    try {
      // Optimistic UI update
      submittedFeedbackMap.set(eventId, feedbackType);
      renderAlertFeed();

      const response = await fetch(`${getApiBaseUrl()}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_id: eventId,
          feedback: feedbackType,
          operator_id: 'op_console_user',
          timestamp: new Date().toISOString()
        })
      });

      if (!response.ok) {
        throw new Error(`Feedback submit failed with status ${response.status}`);
      }

      // Refresh thresholds to reflect bandit online adaptation
      fetchThresholds();
    } catch (err) {
      alert(`Failed to send feedback: ${err.message}`);
      submittedFeedbackMap.delete(eventId);
      renderAlertFeed();
    }
  };

  // --- Simulate Synthetic Events (Demo Feature) ---
  async function simulateEvent(eventType) {
    const isPpe = eventType === 'ppe_violation';
    const payload = {
      camera_id: isPpe ? 'cam_dock_01' : 'cam_perimeter_03',
      zone_id: isPpe ? 'zone_a' : 'zone_b',
      event_type: eventType,
      class: isPpe ? 'no_helmet' : 'person_in_restricted_area',
      confidence: parseFloat((0.72 + Math.random() * 0.22).toFixed(2)),
      tracked_id: `tr_${Math.floor(1000 + Math.random() * 9000)}`,
      timestamp: new Date().toISOString(),
      frame_count_triggered: Math.floor(10 + Math.random() * 20),
      clip_captured: true
    };

    try {
      const res = await fetch(`${getApiBaseUrl()}/events`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        fetchAlerts();
      }
    } catch (err) {
      alert(`Backend unreachable at ${getApiBaseUrl()}`);
    }
  }

  // --- Filter Click Event Listeners ---
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      currentFilter = e.target.getAttribute('data-filter');
      renderAlertFeed();
    });
  });

  btnRefresh.addEventListener('click', () => {
    fetchAlerts();
    fetchThresholds();
    fetchPolicyHistory();
  });

  btnSimPpe.addEventListener('click', () => simulateEvent('ppe_violation'));
  btnSimZone.addEventListener('click', () => simulateEvent('zone_intrusion'));

  // Initial Fetch & Start Polling (every 2s)
  fetchAlerts();
  fetchThresholds();
  fetchPolicyHistory();
  setInterval(() => {
    fetchAlerts();
    fetchThresholds();
  }, 2000);
});

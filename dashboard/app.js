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

  const statusIndicator = document.querySelector('.status-indicator');
  const statusDot = statusIndicator ? statusIndicator.querySelector('.dot') : null;
  const statusLabel = statusIndicator ? statusIndicator.querySelector('.status-label') : null;

  let currentFilter = 'all';
  let activeAlerts = [];
  let submittedFeedbackMap = new Map(); // Track feedback locally for instant UI update
  let isBackendConnected = true;

  function getApiBaseUrl() {
    let url = apiUrlInput.value.trim();
    if (url.endsWith('/')) {
      url = url.slice(0, -1);
    }
    return url;
  }

  // --- Visual Status Indicator ---
  function setSystemStatus(isOnline, reason) {
    isBackendConnected = isOnline;
    if (!statusIndicator) return;
    if (isOnline) {
      statusIndicator.classList.remove('offline');
      if (statusDot) statusDot.className = 'dot live-dot';
      if (statusLabel) statusLabel.textContent = 'SYSTEM LIVE';
    } else {
      statusIndicator.classList.add('offline');
      if (statusDot) statusDot.className = 'dot offline-dot';
      if (statusLabel) statusLabel.textContent = 'BACKEND OFFLINE';
      if (reason) console.warn('System status changed to OFFLINE:', reason);
    }
  }

  // --- Toast Notification Banner ---
  function showToast(message, type = 'error') {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
      <span>${type === 'error' ? '⚠️' : 'ℹ️'}</span>
      <span>${message}</span>
    `;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(12px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // --- Render Offline / Error State ---
  function renderOfflineState(errorMessage) {
    alertCountBadge.textContent = 'Offline';
    alertFeedContainer.innerHTML = `
      <div class="feed-empty-state feed-error-state" id="feed-offline">
        <div class="empty-icon" style="color: var(--color-false);">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        </div>
        <h3 style="color: var(--color-false);">Backend Connection Offline</h3>
        <p style="color: var(--text-muted); margin-top: 6px;">
          Failed to connect to backend API at <code>${getApiBaseUrl()}</code>.<br>
          ${errorMessage ? `<span style="font-size: 11px; color: var(--text-dim);">${errorMessage}</span>` : 'Please verify the backend server is running.'}
        </p>
      </div>
    `;
  }

  // --- Fetch Alerts from Backend ---
  async function fetchAlerts() {
    try {
      const response = await fetch(`${getApiBaseUrl()}/alerts?limit=50`);
      if (!response.ok) throw new Error(`HTTP error ${response.status}`);
      const data = await response.json();
      if (!Array.isArray(data)) throw new Error('Malformed alerts payload: expected an array');
      activeAlerts = data;
      setSystemStatus(true);
      renderAlertFeed();
    } catch (err) {
      console.warn('Failed to fetch alerts:', err.message);
      setSystemStatus(false, err.message);
      renderOfflineState(err.message);
    }
  }

  // --- Fetch Thresholds from Backend ---
  async function fetchThresholds() {
    try {
      const response = await fetch(`${getApiBaseUrl()}/thresholds`);
      if (!response.ok) throw new Error(`HTTP error ${response.status}`);
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
      if (!response.ok) throw new Error(`HTTP error ${response.status}`);
      const history = await response.json();
      if (Array.isArray(history) && history.length > 0) {
        headerPolicyVer.textContent = history[0].policy_version;
      }
      renderPolicyHistory(history);
    } catch (err) {
      console.warn('Failed to fetch policy history:', err.message);
    }
  }

  // --- Render Alert Feed ---
  function renderAlertFeed() {
    // If backend is currently marked offline and we have no cached alerts, keep offline view
    if (!isBackendConnected && activeAlerts.length === 0) {
      renderOfflineState();
      return;
    }

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

    // Per-item resilient rendering loop
    let renderedCount = 0;
    filteredAlerts.forEach((alert, index) => {
      try {
        const card = document.createElement('div');
        const eventType = alert.event_type || 'unknown';
        card.className = `alert-card ${eventType}`;
        card.id = `alert-${alert.event_id || index}`;

        const formattedTime = alert.timestamp
          ? new Date(alert.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
          : 'Unknown';
        const confPercent = typeof alert.confidence === 'number'
          ? Math.round(alert.confidence * 100)
          : 0;

        const isPpe = alert.event_type === 'ppe_violation';
        const typeLabel = isPpe ? 'PPE Violation' : (alert.event_type === 'zone_intrusion' ? 'Zone Intrusion' : 'Security Alert');
        const typeClass = isPpe ? 'type-ppe' : 'type-intrusion';
        const actionClass = alert.bandit_action === 'escalate' ? 'action-escalate' : 'action-log';

        const feedbackState = submittedFeedbackMap.get(alert.event_id);

        const rawClass = alert.class || alert.class_name || 'unknown';
        const displayClass = String(rawClass).replace(/_/g, ' ').toUpperCase();

        card.innerHTML = `
          <div class="alert-main-info">
            <div class="alert-tags">
              <span class="tag ${typeClass}">${typeLabel}</span>
              <span class="tag ${actionClass}">${alert.bandit_action ? alert.bandit_action.toUpperCase() : 'LOG'}</span>
              <span class="tag" style="background: rgba(255,255,255,0.06); color: var(--text-muted);">${alert.zone_id || 'N/A'}</span>
            </div>
            <div class="alert-title">${displayClass} Detected (${alert.camera_id || 'unknown'})</div>
            <div class="alert-meta">
              <span class="meta-item">Confidence: <strong>${confPercent}%</strong>
                <span class="confidence-bar"><span class="confidence-fill" style="width: ${confPercent}%;"></span></span>
              </span>
              <span class="meta-item">Track ID: <code>${alert.tracked_id || 'N/A'}</code></span>
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
        renderedCount++;
      } catch (itemErr) {
        console.error(`Skipping malformed alert item at index ${index}:`, itemErr, alert);
      }
    });

    if (renderedCount === 0 && filteredAlerts.length > 0) {
      alertFeedContainer.innerHTML = '';
      alertFeedContainer.appendChild(feedEmptyState);
      feedEmptyState.style.display = 'block';
    }
  }

  // --- Render Threshold Meters ---
  function renderThresholds(thresholds) {
    if (!thresholds || typeof thresholds !== 'object') return;
    thresholdsContainer.innerHTML = '';
    for (const [zone, val] of Object.entries(thresholds)) {
      const numVal = typeof val === 'number' ? val : 0.70;
      const pct = Math.round(numVal * 100);
      const card = document.createElement('div');
      card.className = 'threshold-card';
      card.innerHTML = `
        <div class="t-head">
          <span class="t-zone">${zone}</span>
          <span class="t-val">${numVal.toFixed(2)}</span>
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
    if (!Array.isArray(history)) return;
    policyHistoryList.innerHTML = '';
    history.forEach(item => {
      const el = document.createElement('div');
      el.className = 'history-item';
      const timeStr = item.trained_at ? new Date(item.trained_at).toLocaleDateString() : 'N/A';
      el.innerHTML = `
        <div>
          <strong style="color: var(--accent-cyan);">${item.policy_version || 'unknown'}</strong>
          <span style="color: var(--text-dim); margin-left: 6px;">${timeStr}</span>
        </div>
        <div style="font-weight: 600; color: var(--color-confirm);">Score: ${item.validation_score ?? 'N/A'}</div>
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
        throw new Error(`Server returned HTTP ${response.status}`);
      }

      showToast(`Feedback '${feedbackType}' recorded for ${eventId.slice(0, 8)}...`, 'info');
      // Refresh thresholds to reflect bandit online adaptation
      fetchThresholds();
    } catch (err) {
      console.error('Failed to submit feedback:', err.message);
      showToast(`Failed to send feedback: ${err.message}`, 'error');
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
      class: isPpe ? 'no_helmet' : 'person_in_zone',
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
      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}`);
      }
      showToast(`Simulated ${isPpe ? 'PPE Violation' : 'Zone Intrusion'} event submitted`, 'info');
      fetchAlerts();
    } catch (err) {
      console.error('Failed to simulate event:', err.message);
      showToast(`Backend unreachable at ${getApiBaseUrl()}: ${err.message}`, 'error');
      setSystemStatus(false, err.message);
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

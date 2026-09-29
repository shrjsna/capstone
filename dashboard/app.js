/**
 * AEGIS Safety Console — JavaScript Application Logic
 *
 * Dynamic API URL: the backend URL is derived from window.location.hostname
 * so the dashboard works whether opened as localhost (on the laptop) or via
 * the LAN IP address from a phone on the same WiFi. Port 8000 is the
 * backend default; port 8080 is this static file server.
 *
 * If the user manually overrides the URL in the input field, that value
 * takes precedence over the auto-derived URL.
 */

// ---------------------------------------------------------------------------
// Dynamic API base URL — works from localhost AND from LAN IP on a phone
// ---------------------------------------------------------------------------
function buildDefaultApiUrl() {
  if (window.location.origin && window.location.origin !== 'null' && !window.location.origin.startsWith('file:')) {
    // If running on port 8080 (legacy manual static server), point to :8000
    if (window.location.port === '8080') {
      return `${window.location.protocol}//${window.location.hostname}:8000`;
    }
    // Single-origin serving: dashboard and backend run on same origin (port 8000)
    return window.location.origin;
  }
  const host = window.location.hostname || '127.0.0.1';
  return `http://${host}:8000`;
}

document.addEventListener('DOMContentLoaded', () => {

  // =========================================================================
  // Element refs
  // =========================================================================
  const apiUrlInput    = document.getElementById('api-url-input');
  const alertFeed      = document.getElementById('alert-feed-container');
  const feedEmpty      = document.getElementById('feed-empty');
  const alertBadge     = document.getElementById('alert-count-badge');
  const btnRefresh     = document.getElementById('btn-refresh');
  const headerPolicy   = document.getElementById('header-policy-ver');
  const thresholds     = document.getElementById('thresholds-container');
  const policyHistory  = document.getElementById('policy-history-list');
  const btnSimPpe      = document.getElementById('btn-sim-ppe');
  const btnSimZone     = document.getElementById('btn-sim-zone');
  const statusIndicator = document.querySelector('.status-indicator');
  const statusDot      = statusIndicator?.querySelector('.dot');
  const statusLabel    = statusIndicator?.querySelector('.status-label');

  // Stream tab
  const sourceTypeSeg  = document.getElementById('source-type-seg');
  const modeSeg        = document.getElementById('mode-seg');
  const sourceInput    = document.getElementById('stream-source-input');
  const sourceLabel    = document.getElementById('source-input-label');
  const sourceHint     = document.getElementById('source-hint');
  const sourceGroup    = document.getElementById('source-input-group');
  const zoneConfigGroup = document.getElementById('zone-config-group');
  const streamZoneSelect = document.getElementById('stream-zone-select');
  const cameraIdInput  = document.getElementById('stream-camera-id');
  const zoneIdInput    = document.getElementById('stream-zone-id');
  const debounceInput  = document.getElementById('stream-debounce');
  const confInput      = document.getElementById('stream-conf');
  const btnStreamStart = document.getElementById('btn-stream-start');
  const btnStreamStop  = document.getElementById('btn-stream-stop');
  const streamErrorBox = document.getElementById('stream-error-box');
  const streamInfo     = document.getElementById('stream-info');
  const infoSource     = document.getElementById('info-source');
  const infoMode       = document.getElementById('info-mode');
  const streamBadge    = document.getElementById('stream-status-badge');
  const streamImg      = document.getElementById('stream-img');
  const streamPlaceholder = document.getElementById('stream-placeholder');
  const streamLiveDot  = document.getElementById('stream-live-dot');
  const streamLiveLabel = document.getElementById('stream-live-label');
  const streamRecentEvents = document.getElementById('stream-recent-events');

  // Zone draw tab
  const captureSource  = document.getElementById('zone-capture-source');
  const zoneSourcePresets = document.getElementById('zone-source-presets');
  const btnCapture     = document.getElementById('btn-capture-frame');
  const btnLivePreview = document.getElementById('btn-live-stream-preview');
  const zoneCameraId   = document.getElementById('zone-camera-id');
  const zoneZoneId     = document.getElementById('zone-zone-id');
  const btnModeBox     = document.getElementById('btn-mode-box');
  const btnModePoly    = document.getElementById('btn-mode-poly');
  const btnPresetCenter = document.getElementById('btn-preset-center');
  const btnPresetFloor = document.getElementById('btn-preset-floor');
  const zoneCanvas     = document.getElementById('zone-canvas');
  const canvasContainer = document.getElementById('canvas-container');
  const canvasPlaceholder = document.getElementById('canvas-placeholder');
  const canvasHint     = document.getElementById('canvas-hint');
  const zoneStatusBadge = document.getElementById('zone-status-badge');
  const btnZoneUndo    = document.getElementById('btn-zone-undo');
  const btnZoneClear   = document.getElementById('btn-zone-clear');
  const btnZoneSave    = document.getElementById('btn-zone-save');
  const btnStartZoneDetect = document.getElementById('btn-start-zone-detect');
  const pointCount     = document.getElementById('zone-point-count');
  const zoneSaveResult = document.getElementById('zone-save-result');
  const zonesList      = document.getElementById('zones-list');
  const btnRefreshZones = document.getElementById('btn-refresh-zones');

  // =========================================================================
  // State
  // =========================================================================
  let activeAlerts     = [];
  let currentFilter    = 'all';
  let feedbackMap      = new Map();
  let isConnected      = true;
  let activeSourceType = 'webcam';
  let activeMode       = 'ppe';
  let isStreaming      = false;
  let streamCameraId   = 'stream_cam_01';

  // Zone draw state
  let zonePoints       = [];            // [{x,y}] canvas-coordinate polygon points
  let capturedImageData = null;
  let canvasCtx        = null;
  let activeZoneType   = 'restricted';  // 'restricted' | 'warning' | 'custom'
  let activeZoneColor  = '#ef4444';     // Red for danger
  let drawMode         = 'box';         // 'box' | 'polygon'
  let isDragging       = false;
  let dragStart        = {x: 0, y: 0};
  let dragCurrent      = {x: 0, y: 0};
  let mouseHoverPoint  = null;
  let isLivePreview    = false;
  let livePreviewTimer = null;

  // =========================================================================
  // Dynamic API URL
  // =========================================================================
  // Set default on load — phone on LAN automatically gets the right IP
  apiUrlInput.value = buildDefaultApiUrl();

  function getApiBase() {
    return (apiUrlInput.value || '').trim().replace(/\/$/, '');
  }

  // =========================================================================
  // Tab switching
  // =========================================================================
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.getAttribute('data-tab');
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${tab}`)?.classList.add('active');
      if (tab === 'zones') loadZonesList();
      if (tab === 'stream') loadZonesForStream();
      if (tab === 'control') {
        loadProcessStatus();
        startProcessPolling();
      } else {
        stopProcessPolling();
      }
    });
  });

  // =========================================================================
  // System status / offline indicator
  // =========================================================================
  function setStatus(online, reason) {
    isConnected = online;
    if (!statusIndicator) return;
    if (online) {
      statusIndicator.classList.remove('offline');
      if (statusDot) statusDot.className = 'dot live-dot';
      if (statusLabel) statusLabel.textContent = 'SYSTEM LIVE';
    } else {
      statusIndicator.classList.add('offline');
      if (statusDot) statusDot.className = 'dot offline-dot';
      if (statusLabel) statusLabel.textContent = 'BACKEND OFFLINE';
      if (reason) console.warn('Offline:', reason);
    }
  }

  function showToast(msg, type = 'error') {
    let c = document.getElementById('toast-container');
    if (!c) { c = document.createElement('div'); c.id = 'toast-container'; document.body.appendChild(c); }
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    t.innerHTML = `<span>${type === 'error' ? '⚠️' : 'ℹ️'}</span><span>${msg}</span>`;
    c.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateY(12px)'; t.style.transition = 'all 0.3s ease'; setTimeout(() => t.remove(), 300); }, 4000);
  }

  function renderOffline(errMsg) {
    alertBadge.textContent = 'Offline';
    alertFeed.innerHTML = `
      <div class="feed-empty-state feed-error-state">
        <div class="empty-icon" style="color:var(--color-false);">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        </div>
        <h3 style="color:var(--color-false);">Backend Connection Offline</h3>
        <p style="color:var(--text-muted);margin-top:6px;">
          Cannot reach <code>${getApiBase()}</code>.<br>
          ${errMsg ? `<span style="font-size:11px;color:var(--text-dim);">${errMsg}</span>` : 'Start the backend server first.'}
        </p>
      </div>`;
  }

  // =========================================================================
  // Alert feed
  // =========================================================================
  async function fetchAlerts() {
    try {
      const r = await fetch(`${getApiBase()}/alerts?limit=50`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      if (!Array.isArray(data)) throw new Error('Expected array');
      activeAlerts = data;
      setStatus(true);
      renderAlertFeed();
      updateStreamRecentEvents();
    } catch (e) {
      setStatus(false, e.message);
      renderOffline(e.message);
    }
  }

  async function fetchThresholds() {
    try {
      const r = await fetch(`${getApiBase()}/thresholds`);
      if (!r.ok) return;
      renderThresholds(await r.json());
    } catch (_) {}
  }

  async function fetchPolicyHistory() {
    try {
      const r = await fetch(`${getApiBase()}/policy-history`);
      if (!r.ok) return;
      const h = await r.json();
      if (Array.isArray(h) && h.length > 0) headerPolicy.textContent = h[0].policy_version;
      renderPolicyHistory(h);
    } catch (_) {}
  }

  function renderAlertFeed() {
    if (!isConnected && activeAlerts.length === 0) { renderOffline(); return; }

    const filtered = activeAlerts.filter(a =>
      currentFilter === 'all' ? true : a.event_type === currentFilter
    );
    alertBadge.textContent = `${filtered.length} Alerts`;

    if (filtered.length === 0) {
      alertFeed.innerHTML = '';
      alertFeed.appendChild(feedEmpty);
      feedEmpty.style.display = 'block';
      return;
    }
    feedEmpty.style.display = 'none';
    alertFeed.innerHTML = '';

    filtered.forEach((alert, idx) => {
      try {
        const card = document.createElement('div');
        card.className = `alert-card ${alert.event_type || 'unknown'}`;
        card.id = `alert-${alert.event_id || idx}`;
        const time = alert.timestamp ? new Date(alert.timestamp).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '—';
        const conf = typeof alert.confidence === 'number' ? Math.round(alert.confidence * 100) : 0;
        const isPpe = alert.event_type === 'ppe_violation';
        const typeLabel = isPpe ? 'PPE Violation' : (alert.event_type === 'zone_intrusion' ? 'Zone Intrusion' : 'Security Alert');
        const typeClass = isPpe ? 'type-ppe' : 'type-intrusion';
        const actionClass = alert.bandit_action === 'escalate' ? 'action-escalate' : 'action-log';
        const fbState = feedbackMap.get(alert.event_id);
        const rawClass = alert.class || alert.class_name || 'unknown';
        const dispClass = String(rawClass).replace(/_/g, ' ').toUpperCase();

        card.innerHTML = `
          <div class="alert-main-info">
            <div class="alert-tags">
              <span class="tag ${typeClass}">${typeLabel}</span>
              <span class="tag ${actionClass}">${(alert.bandit_action || 'log').toUpperCase()}</span>
              <span class="tag" style="background:rgba(255,255,255,0.06);color:var(--text-muted);">${alert.zone_id || 'N/A'}</span>
            </div>
            <div class="alert-title">${dispClass} Detected (${alert.camera_id || 'unknown'})</div>
            <div class="alert-meta">
              <span class="meta-item">Confidence: <strong>${conf}%</strong>
                <span class="confidence-bar"><span class="confidence-fill" style="width:${conf}%;"></span></span>
              </span>
              <span class="meta-item">Track: <code>${alert.tracked_id || 'N/A'}</code></span>
              <span class="meta-item">${time}</span>
            </div>
          </div>
          <div class="alert-actions">
            ${fbState ? `<div class="feedback-status-badge ${fbState}">${fbState === 'confirmed' ? '✓ CONFIRMED' : '✗ FALSE ALARM'}</div>` : `
              <button class="btn-feedback btn-confirm" onclick="submitFeedback('${alert.event_id}','confirmed')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>Confirm
              </button>
              <button class="btn-feedback btn-false-alarm" onclick="submitFeedback('${alert.event_id}','false_alarm')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>False Alarm
              </button>`}
          </div>`;
        alertFeed.appendChild(card);
      } catch (e) {
        console.warn('Alert render error:', e);
      }
    });
  }

  function renderThresholds(data) {
    if (!data || typeof data !== 'object') return;
    thresholds.innerHTML = '';
    for (const [zone, val] of Object.entries(data)) {
      const v = typeof val === 'number' ? val : 0.7;
      const pct = Math.round(v * 100);
      const el = document.createElement('div');
      el.className = 'threshold-card';
      el.innerHTML = `<div class="t-head"><span class="t-zone">${zone}</span><span class="t-val">${v.toFixed(2)}</span></div><div class="meter-bar"><div class="meter-fill" style="width:${pct}%;"></div></div>`;
      thresholds.appendChild(el);
    }
  }

  function renderPolicyHistory(data) {
    if (!Array.isArray(data)) return;
    policyHistory.innerHTML = '';
    data.forEach(item => {
      const el = document.createElement('div');
      el.className = 'history-item';
      const ts = item.trained_at ? new Date(item.trained_at).toLocaleDateString() : 'N/A';
      el.innerHTML = `<div><strong style="color:var(--accent-cyan);">${item.policy_version || '—'}</strong><span style="color:var(--text-dim);margin-left:6px;">${ts}</span></div><div style="font-weight:600;color:var(--color-confirm);">Score: ${item.validation_score ?? 'N/A'}</div>`;
      policyHistory.appendChild(el);
    });
  }

  // =========================================================================
  // Feedback
  // =========================================================================
  window.submitFeedback = async function(eventId, fbType) {
    try {
      feedbackMap.set(eventId, fbType);
      renderAlertFeed();
      const r = await fetch(`${getApiBase()}/feedback`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({event_id: eventId, feedback: fbType, operator_id: 'op_console_user', timestamp: new Date().toISOString()})
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      showToast(`Feedback '${fbType}' recorded`, 'info');
      fetchThresholds();
    } catch (e) {
      showToast(`Feedback failed: ${e.message}`, 'error');
      feedbackMap.delete(eventId);
      renderAlertFeed();
    }
  };

  // =========================================================================
  // Simulate events
  // =========================================================================
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
      clip_captured: false
    };
    try {
      const r = await fetch(`${getApiBase()}/events`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      showToast(`Simulated ${isPpe ? 'PPE' : 'Zone'} event`, 'info');
      fetchAlerts();
    } catch (e) {
      showToast(`Backend unreachable: ${e.message}`, 'error');
      setStatus(false, e.message);
    }
  }

  // =========================================================================
  // Live Stream tab — source type / mode selectors
  // =========================================================================
  sourceTypeSeg.querySelectorAll('.seg-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      sourceTypeSeg.querySelectorAll('.seg-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeSourceType = btn.getAttribute('data-val');
      updateSourceInputUI();
    });
  });

  modeSeg.querySelectorAll('.seg-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      modeSeg.querySelectorAll('.seg-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeMode = btn.getAttribute('data-val');
      zoneConfigGroup.style.display = activeMode === 'zone_intrusion' ? '' : 'none';
    });
  });

  function updateSourceInputUI() {
    if (activeSourceType === 'webcam') {
      sourceLabel.textContent = 'Camera Index';
      sourceInput.value = '0';
      sourceInput.placeholder = '0';
      sourceHint.textContent = 'Enter 0 for default webcam, 1 for external USB camera.';
    } else if (activeSourceType === 'rtsp') {
      sourceLabel.textContent = 'RTSP / HTTP URL';
      sourceInput.value = '';
      sourceInput.placeholder = 'rtsp://192.168.1.50:554/stream1';
      sourceHint.textContent = 'Full RTSP or HTTP stream URL. For a phone IP Webcam app: http://192.168.x.x:8080/video';
    } else {
      sourceLabel.textContent = 'Video File Path';
      sourceInput.value = '';
      sourceInput.placeholder = 'demo/videos/zone_intrusion_demo.mp4';
      sourceHint.textContent = 'Relative to repo root. Video files loop automatically.';
    }
  }

  async function loadZonesForStream() {
    try {
      const r = await fetch(`${getApiBase()}/zones`);
      if (!r.ok) return;
      const zones = await r.json();
      streamZoneSelect.innerHTML = '';
      if (zones.length === 0) {
        streamZoneSelect.innerHTML = '<option value="">No zones saved — use Draw Zone tab</option>';
      } else {
        zones.forEach(z => {
          const opt = document.createElement('option');
          opt.value = z.file_path;
          opt.textContent = `${z.zone_id} (${z.camera_id}, ${z.point_count} pts)`;
          streamZoneSelect.appendChild(opt);
        });
      }
    } catch (_) {}
  }

  // =========================================================================
  // Start / stop stream
  // =========================================================================
  btnStreamStart.addEventListener('click', async () => {
    const source = sourceInput.value.trim();
    if (!source) { showToast('Enter a source first.', 'error'); return; }

    const zoneConfigPath = activeMode === 'zone_intrusion' ? (streamZoneSelect.value || null) : null;

    streamCameraId = cameraIdInput.value.trim() || 'stream_cam_01';

    const body = {
      source,
      mode: activeMode,
      camera_id: streamCameraId,
      zone_id: zoneIdInput.value.trim() || 'zone_A',
      zone_config_path: zoneConfigPath,
      debounce_frames: parseInt(debounceInput.value) || 3,
      conf_threshold: parseFloat(confInput.value) || 0.25,
    };

    btnStreamStart.disabled = true;
    btnStreamStart.textContent = 'Starting…';
    streamErrorBox.style.display = 'none';

    try {
      const r = await fetch(`${getApiBase()}/stream/start`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)
      });
      const data = await r.json();
      if (!r.ok || !data.started) {
        throw new Error(data.detail || data.error || `HTTP ${r.status}`);
      }
      // Stream started — point <img> at the MJPEG endpoint
      isStreaming = true;
      const mjpegUrl = `${getApiBase()}/stream/mjpeg`;
      streamImg.src = mjpegUrl;
      streamImg.style.display = 'block';
      streamPlaceholder.style.display = 'none';
      streamErrorBox.style.display = 'none';
      streamInfo.style.display = 'block';
      infoSource.textContent = source;
      infoMode.textContent = activeMode === 'ppe' ? 'PPE Detection' : 'Zone Intrusion';
      setStreamBadge('live');
      btnStreamStop.disabled = false;
      btnStreamStart.textContent = 'Restart Stream';
      btnStreamStart.disabled = false;
      showToast('Stream started', 'info');
    } catch (e) {
      streamErrorBox.textContent = `Could not start stream: ${e.message}`;
      streamErrorBox.style.display = 'block';
      setStreamBadge('error');
      btnStreamStart.textContent = 'Start Stream';
      btnStreamStart.disabled = false;
    }
  });

  btnStreamStop.addEventListener('click', async () => {
    try {
      await fetch(`${getApiBase()}/stream/stop`, {method: 'POST'});
    } catch (_) {}
    stopStreamUI();
    showToast('Stream stopped', 'info');
  });

  function stopStreamUI() {
    isStreaming = false;
    streamImg.src = '';
    streamImg.style.display = 'none';
    streamPlaceholder.style.display = '';
    streamInfo.style.display = 'none';
    streamErrorBox.style.display = 'none';
    setStreamBadge('stopped');
    btnStreamStop.disabled = true;
    btnStreamStart.textContent = 'Start Stream';
  }

  function setStreamBadge(state) {
    streamBadge.className = `stream-badge ${state}`;
    const labels = {live: 'LIVE', stopped: 'STOPPED', error: 'ERROR'};
    streamBadge.textContent = labels[state] || state.toUpperCase();
    streamLiveDot.className = `stream-live-indicator ${state === 'live' ? 'live' : 'offline'}`;
    streamLiveLabel.textContent = state === 'live' ? 'Streaming' : state === 'error' ? 'Error' : 'Not streaming';
  }

  // Detect when the MJPEG img fails to load (stream stopped / backend down)
  streamImg.addEventListener('error', () => {
    if (isStreaming) {
      streamErrorBox.textContent = 'Stream disconnected. The backend may have stopped or the source ended.';
      streamErrorBox.style.display = 'block';
      setStreamBadge('error');
    }
  });

  function updateStreamRecentEvents() {
    if (!streamRecentEvents || !isStreaming) return;
    const recent = activeAlerts
      .filter(a => a.camera_id === streamCameraId)
      .slice(0, 4);
    streamRecentEvents.innerHTML = '';
    if (recent.length === 0) return;
    recent.forEach(a => {
      const el = document.createElement('div');
      el.className = 'stream-event-chip ' + (a.event_type === 'ppe_violation' ? 'ppe' : 'zone');
      const cls = (a.class || a.class_name || '').replace(/_/g,' ').toUpperCase();
      const conf = Math.round((a.confidence || 0) * 100);
      el.textContent = `${cls} ${conf}%`;
      streamRecentEvents.appendChild(el);
    });
  }

  // =========================================================================
  // Zone Draw tab
  // =========================================================================
  canvasCtx = zoneCanvas.getContext('2d');

  function getCanvasCoords(e) {
    const rect = zoneCanvas.getBoundingClientRect();
    const scaleX = zoneCanvas.width / (rect.width || 1);
    const scaleY = zoneCanvas.height / (rect.height || 1);
    const rawX = (e.clientX - rect.left) * scaleX;
    const rawY = (e.clientY - rect.top) * scaleY;
    return {
      x: Math.max(0, Math.min(zoneCanvas.width, Math.round(rawX))),
      y: Math.max(0, Math.min(zoneCanvas.height, Math.round(rawY))),
    };
  }

  // Camera source presets sync
  if (zoneSourcePresets) {
    zoneSourcePresets.addEventListener('change', () => {
      if (zoneSourcePresets.value === 'custom') {
        captureSource.focus();
      } else {
        captureSource.value = zoneSourcePresets.value;
      }
    });
  }

  // Zone type options (Red / Yellow / Blue)
  document.querySelectorAll('.zone-type-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.zone-type-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      activeZoneType = pill.getAttribute('data-type') || 'restricted';
      activeZoneColor = pill.getAttribute('data-color') || '#ef4444';
      const presetId = pill.getAttribute('data-zoneid');
      if (presetId) {
        zoneZoneId.value = presetId;
      }
      redrawCanvas();
    });
  });

  // Marking mode (Box vs Polygon)
  if (btnModeBox) {
    btnModeBox.addEventListener('click', () => {
      drawMode = 'box';
      btnModeBox.classList.add('active');
      btnModePoly?.classList.remove('active');
      if (canvasHint) canvasHint.textContent = 'Click & drag on the image to mark a restricted box';
      mouseHoverPoint = null;
      redrawCanvas();
    });
  }

  if (btnModePoly) {
    btnModePoly.addEventListener('click', () => {
      drawMode = 'polygon';
      btnModePoly.classList.add('active');
      btnModeBox?.classList.remove('active');
      if (canvasHint) canvasHint.textContent = 'Click on the image to add polygon boundary points';
      redrawCanvas();
    });
  }

  // Presets: Center Box & Floor Hazard
  if (btnPresetCenter) {
    btnPresetCenter.addEventListener('click', () => {
      const w = zoneCanvas.width || 640;
      const h = zoneCanvas.height || 480;
      zonePoints = [
        {x: Math.round(w * 0.25), y: Math.round(h * 0.25)},
        {x: Math.round(w * 0.75), y: Math.round(h * 0.25)},
        {x: Math.round(w * 0.75), y: Math.round(h * 0.75)},
        {x: Math.round(w * 0.25), y: Math.round(h * 0.75)},
      ];
      updatePointCountUI();
      redrawCanvas();
      showToast('Center box marked! Click "Detect Anyone Who Enters" to start monitoring.', 'info');
    });
  }

  if (btnPresetFloor) {
    btnPresetFloor.addEventListener('click', () => {
      const w = zoneCanvas.width || 640;
      const h = zoneCanvas.height || 480;
      zonePoints = [
        {x: Math.round(w * 0.05), y: Math.round(h * 0.55)},
        {x: Math.round(w * 0.95), y: Math.round(h * 0.55)},
        {x: Math.round(w * 0.95), y: Math.round(h * 0.95)},
        {x: Math.round(w * 0.05), y: Math.round(h * 0.95)},
      ];
      updatePointCountUI();
      redrawCanvas();
      showToast('Floor hazard area marked! Click "Detect Anyone Who Enters".', 'info');
    });
  }

  function setupCanvasWithImage(img) {
    const containerW = canvasContainer.clientWidth - 2;
    const containerH = canvasContainer.clientHeight - 2;
    const scale = Math.min(containerW / (img.width || 640), containerH / (img.height || 480), 1);
    zoneCanvas.width  = Math.round((img.width || 640)  * scale);
    zoneCanvas.height = Math.round((img.height || 480) * scale);
    zoneCanvas._imgElement = img;
    zoneCanvas._scale = scale;
    zoneCanvas._naturalW = img.width || 640;
    zoneCanvas._naturalH = img.height || 480;

    canvasPlaceholder.style.display = 'none';
    zoneCanvas.style.display = 'block';
    if (zoneStatusBadge) {
      zoneStatusBadge.className = 'proc-badge badge-running';
      zoneStatusBadge.textContent = 'IMAGE READY';
    }
    redrawCanvas();
  }

  // Still Frame Capture
  btnCapture.addEventListener('click', async () => {
    const src = captureSource.value.trim();
    if (!src) { showToast('Enter a camera source.', 'error'); return; }

    btnCapture.disabled = true;
    btnCapture.textContent = 'Capturing…';

    try {
      const r = await fetch(`${getApiBase()}/capture-frame?source=${encodeURIComponent(src)}`);
      if (!r.ok) {
        const err = await r.json().catch(() => ({detail: `HTTP ${r.status}`}));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }

      const blob = await r.blob();
      const imgUrl = URL.createObjectURL(blob);
      const img = new Image();
      img.onload = () => {
        setupCanvasWithImage(img);
        zonePoints = [];
        updatePointCountUI();
        showToast('Frame captured — drag a box or click points to mark zone', 'info');
      };
      img.onerror = () => { throw new Error('Could not decode captured frame.'); };
      img.src = imgUrl;
    } catch (e) {
      showToast(`Capture failed: ${e.message}`, 'error');
    } finally {
      btnCapture.disabled = false;
      btnCapture.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>Capture Frame`;
    }
  });

  // Live Stream Preview
  if (btnLivePreview) {
    btnLivePreview.addEventListener('click', () => {
      const src = captureSource.value.trim() || '0';
      if (isLivePreview) {
        // Stop preview
        isLivePreview = false;
        if (livePreviewTimer) clearInterval(livePreviewTimer);
        livePreviewTimer = null;
        btnLivePreview.classList.remove('active');
        btnLivePreview.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>Live Preview`;
        if (zoneStatusBadge) {
          zoneStatusBadge.className = 'proc-badge badge-stopped';
          zoneStatusBadge.textContent = 'READY';
        }
        showToast('Live preview paused — frame ready for marking', 'info');
      } else {
        // Start preview
        isLivePreview = true;
        btnLivePreview.classList.add('active');
        btnLivePreview.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>Pause Frame`;
        if (zoneStatusBadge) {
          zoneStatusBadge.className = 'proc-badge badge-running';
          zoneStatusBadge.textContent = 'LIVE PREVIEW';
        }

        const grab = async () => {
          if (!isLivePreview) return;
          try {
            const r = await fetch(`${getApiBase()}/capture-frame?source=${encodeURIComponent(src)}`);
            if (!r.ok) return;
            const blob = await r.blob();
            const imgUrl = URL.createObjectURL(blob);
            const img = new Image();
            img.onload = () => {
              setupCanvasWithImage(img);
            };
            img.src = imgUrl;
          } catch (_) {}
        };
        grab();
        livePreviewTimer = setInterval(grab, 600);
        showToast('Live camera preview active — click Pause to freeze', 'info');
      }
    });
  }

  // Canvas Mouse Interactions (Drag Box + Click Points)
  zoneCanvas.addEventListener('mousedown', e => {
    if (!zoneCanvas._imgElement) {
      showToast('Capture a frame or start Live Preview first.', 'info');
      return;
    }
    if (drawMode === 'box') {
      isDragging = true;
      dragStart = getCanvasCoords(e);
      dragCurrent = dragStart;
    }
  });

  zoneCanvas.addEventListener('mousemove', e => {
    const pt = getCanvasCoords(e);
    if (isDragging && drawMode === 'box') {
      dragCurrent = pt;
      redrawCanvas();
    } else if (drawMode === 'polygon' && zonePoints.length > 0) {
      mouseHoverPoint = pt;
      redrawCanvas();
    }
  });

  window.addEventListener('mouseup', e => {
    if (isDragging && drawMode === 'box') {
      isDragging = false;
      const pt = getCanvasCoords(e);
      const x1 = Math.min(dragStart.x, pt.x);
      const x2 = Math.max(dragStart.x, pt.x);
      const y1 = Math.min(dragStart.y, pt.y);
      const y2 = Math.max(dragStart.y, pt.y);
      if ((x2 - x1) >= 15 && (y2 - y1) >= 15) {
        zonePoints = [
          {x: x1, y: y1},
          {x: x2, y: y1},
          {x: x2, y: y2},
          {x: x1, y: y2},
        ];
        updatePointCountUI();
        redrawCanvas();
        showToast(`Marked ${zoneZoneId.value} restricted zone! Click "Detect Anyone Who Enters".`, 'info');
      }
    }
  });

  zoneCanvas.addEventListener('click', e => {
    if (drawMode !== 'polygon') return;
    if (!zoneCanvas._imgElement) {
      showToast('Capture a frame or start Live Preview first.', 'info');
      return;
    }
    const pt = getCanvasCoords(e);
    if (zonePoints.length >= 3) {
      const d0 = Math.hypot(pt.x - zonePoints[0].x, pt.y - zonePoints[0].y);
      if (d0 < 22) {
        showToast('Polygon boundary closed!', 'info');
        mouseHoverPoint = null;
        redrawCanvas();
        return;
      }
    }
    zonePoints.push(pt);
    updatePointCountUI();
    redrawCanvas();
  });

  function redrawCanvas() {
    if (!canvasCtx || !zoneCanvas._imgElement) return;
    const ctx = canvasCtx;
    ctx.clearRect(0, 0, zoneCanvas.width, zoneCanvas.height);

    // Draw background video frame
    ctx.drawImage(zoneCanvas._imgElement, 0, 0, zoneCanvas.width, zoneCanvas.height);

    const mainColor = activeZoneColor || '#ef4444';

    // 1. Draw Dragging Box Preview
    if (isDragging && drawMode === 'box') {
      const x1 = Math.min(dragStart.x, dragCurrent.x);
      const y1 = Math.min(dragStart.y, dragCurrent.y);
      const w = Math.abs(dragCurrent.x - dragStart.x);
      const h = Math.abs(dragCurrent.y - dragStart.y);

      ctx.fillStyle = activeZoneType === 'restricted' ? 'rgba(239, 68, 68, 0.25)' : 'rgba(251, 191, 36, 0.25)';
      ctx.fillRect(x1, y1, w, h);

      ctx.strokeStyle = mainColor;
      ctx.lineWidth = 2.5;
      ctx.setLineDash([6, 4]);
      ctx.strokeRect(x1, y1, w, h);
      ctx.setLineDash([]);

      // Label with dimensions
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 11px Inter, sans-serif';
      ctx.fillText(`${w}x${h}px`, x1 + 6, y1 + 16);
      return;
    }

    if (zonePoints.length === 0) return;

    // 2. Fill Semi-transparent Zone
    if (zonePoints.length >= 3) {
      ctx.beginPath();
      ctx.moveTo(zonePoints[0].x, zonePoints[0].y);
      zonePoints.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
      ctx.closePath();
      ctx.fillStyle = activeZoneType === 'restricted' ? 'rgba(239, 68, 68, 0.22)' : 'rgba(251, 191, 36, 0.22)';
      ctx.fill();
    }

    // 3. Draw Polygon Edges
    ctx.beginPath();
    ctx.strokeStyle = mainColor;
    ctx.lineWidth = 2.5;
    ctx.setLineDash([]);
    ctx.moveTo(zonePoints[0].x, zonePoints[0].y);
    zonePoints.slice(1).forEach(p => ctx.lineTo(p.x, p.y));

    if (zonePoints.length >= 3) {
      ctx.setLineDash([5, 4]);
      ctx.lineTo(zonePoints[0].x, zonePoints[0].y);
      ctx.setLineDash([]);
    }
    ctx.stroke();

    // 4. Polygon Guide line to mouse
    if (drawMode === 'polygon' && mouseHoverPoint && zonePoints.length > 0) {
      ctx.beginPath();
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.7)';
      ctx.lineWidth = 1.5;
      const last = zonePoints[zonePoints.length - 1];
      ctx.moveTo(last.x, last.y);
      ctx.lineTo(mouseHoverPoint.x, mouseHoverPoint.y);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // 5. Draw Vertices
    zonePoints.forEach((p, i) => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 6, 0, Math.PI * 2);
      ctx.fillStyle = i === 0 ? '#10b981' : mainColor;
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Vertex Index label
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 11px Inter, sans-serif';
      ctx.fillText(i + 1, p.x + 8, p.y - 6);
    });

    // 6. Zone Name Label
    if (zonePoints.length >= 1) {
      const p0 = zonePoints[0];
      const zName = zoneZoneId.value.trim() || 'RESTRICTED ZONE';
      ctx.fillStyle = mainColor;
      ctx.beginPath();
      ctx.roundRect ? ctx.roundRect(p0.x, Math.max(10, p0.y - 28), ctx.measureText(zName).width + 16, 20, 4) : ctx.rect(p0.x, Math.max(10, p0.y - 28), ctx.measureText(zName).width + 16, 20);
      ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 11px Inter, sans-serif';
      ctx.fillText(zName, p0.x + 8, Math.max(24, p0.y - 14));
    }
  }

  function updatePointCountUI() {
    if (pointCount) pointCount.textContent = zonePoints.length;
    if (btnZoneUndo) btnZoneUndo.disabled = zonePoints.length === 0;
    if (btnZoneClear) btnZoneClear.disabled = zonePoints.length === 0;
    if (btnZoneSave) btnZoneSave.disabled = zonePoints.length < 3;
    if (btnStartZoneDetect) btnStartZoneDetect.disabled = zonePoints.length < 3;
  }

  btnZoneUndo.addEventListener('click', () => {
    zonePoints.pop();
    updatePointCountUI();
    redrawCanvas();
  });

  btnZoneClear.addEventListener('click', () => {
    zonePoints = [];
    updatePointCountUI();
    redrawCanvas();
  });

  // Save Zone Helper Function
  async function saveCurrentZone() {
    if (zonePoints.length < 3) return null;
    const camId  = zoneCameraId.value.trim() || 'cam_01';
    const zoneId = zoneZoneId.value.trim()   || 'zone_red_1';
    const scale  = zoneCanvas._scale || 1;

    const nativePolygon = zonePoints.map(p => [
      Math.round(p.x / scale),
      Math.round(p.y / scale),
    ]);

    try {
      const r = await fetch(`${getApiBase()}/zones`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          camera_id: camId,
          zone_id: zoneId,
          polygon: nativePolygon,
          frame_width:  zoneCanvas._naturalW || null,
          frame_height: zoneCanvas._naturalH || null,
        })
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({detail: `HTTP ${r.status}`}));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      const saved = await r.json();
      zoneSaveResult.style.display = 'block';
      zoneSaveResult.className = 'zone-save-result success';
      zoneSaveResult.innerHTML = `<strong>Zone saved:</strong> ${saved.filename}<br><span style="font-size:11px;color:var(--text-dim);">${saved.point_count} points · ${camId} / ${zoneId}</span>`;
      showToast(`Zone '${zoneId}' saved`, 'info');
      loadZonesList();
      return saved;
    } catch (e) {
      zoneSaveResult.style.display = 'block';
      zoneSaveResult.className = 'zone-save-result error';
      zoneSaveResult.textContent = `Save failed: ${e.message}`;
      return null;
    }
  }

  btnZoneSave.addEventListener('click', async () => {
    await saveCurrentZone();
  });

  // "Detect Anyone Who Enters" - Complete Workflow
  if (btnStartZoneDetect) {
    btnStartZoneDetect.addEventListener('click', async () => {
      if (zonePoints.length < 3) {
        showToast('Please mark at least 3 points or drag a box first.', 'error');
        return;
      }

      btnStartZoneDetect.disabled = true;
      btnStartZoneDetect.textContent = 'Configuring Intrusion Detection…';

      // 1. Save zone
      const saved = await saveCurrentZone();
      if (!saved) {
        btnStartZoneDetect.disabled = false;
        btnStartZoneDetect.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>Detect Anyone Who Enters`;
        return;
      }

      showToast(`Zone saved! Launching intrusion detection on ${saved.zone_id}...`, 'info');

      // 2. Switch to Live Stream tab
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      const streamTabBtn = document.querySelector('.tab-btn[data-tab="stream"]');
      if (streamTabBtn) streamTabBtn.classList.add('active');
      const tabStreamEl = document.getElementById('tab-stream');
      if (tabStreamEl) tabStreamEl.classList.add('active');

      // 3. Switch mode to Zone Intrusion
      activeMode = 'zone_intrusion';
      document.querySelectorAll('.mode-btn').forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-mode') === 'zone_intrusion');
      });
      if (zoneConfigGroup) zoneConfigGroup.style.display = 'flex';

      // 4. Configure camera source & camera ID
      if (sourceInput) sourceInput.value = captureSource.value.trim() || '0';
      if (cameraIdInput) cameraIdInput.value = zoneCameraId.value.trim() || 'cam_01';
      if (zoneIdInput) zoneIdInput.value = zoneZoneId.value.trim() || 'zone_red_1';

      // 5. Refresh zones dropdown and select newly saved zone
      await loadZonesForStream();
      if (streamZoneSelect && saved.file_path) {
        streamZoneSelect.value = saved.file_path;
      }

      // 6. Launch Live Stream
      setTimeout(() => {
        btnStreamStart.click();
        btnStartZoneDetect.disabled = false;
        btnStartZoneDetect.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>Detect Anyone Who Enters`;
      }, 350);
    });
  }

  // Saved zones list loader
  async function loadZonesList() {
    try {
      const r = await fetch(`${getApiBase()}/zones`);
      if (!r.ok) { zonesList.innerHTML = '<p style="font-size:12px;color:var(--text-dim);">Could not load zones.</p>'; return; }
      const zones = await r.json();
      zonesList.innerHTML = '';
      if (zones.length === 0) {
        zonesList.innerHTML = '<p style="font-size:12px;color:var(--text-dim);">No saved zones yet. Mark one above.</p>';
        return;
      }
      zones.forEach(z => {
        const el = document.createElement('div');
        el.className = 'zone-list-item';
        el.innerHTML = `
          <div class="zone-list-info">
            <span class="zone-list-name">${z.zone_id}</span>
            <span class="zone-list-meta">${z.camera_id} · ${z.point_count} pts</span>
            <span class="zone-list-file">${z.filename}</span>
          </div>
          <div class="zone-list-actions">
            <button class="btn-zone-action-load" title="Load and view on canvas" data-poly='${JSON.stringify(z.polygon || [])}' data-cam="${z.camera_id}" data-zone="${z.zone_id}">
              Load
            </button>
            <button class="btn-zone-action-detect" title="Run live intrusion detection" data-file="${z.file_path}" data-cam="${z.camera_id}" data-zone="${z.zone_id}">
              ▶ Detect
            </button>
            <button class="btn-icon zone-delete-btn" title="Delete zone" data-cam="${z.camera_id}" data-zone="${z.zone_id}">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
              </svg>
            </button>
          </div>`;

        // Load onto canvas
        el.querySelector('.btn-zone-action-load').addEventListener('click', e => {
          const polyStr = e.currentTarget.getAttribute('data-poly');
          const cam = e.currentTarget.getAttribute('data-cam');
          const zone = e.currentTarget.getAttribute('data-zone');
          try {
            const poly = JSON.parse(polyStr);
            const scale = zoneCanvas._scale || 1;
            zonePoints = poly.map(pt => ({
              x: Math.round(pt[0] * scale),
              y: Math.round(pt[1] * scale),
            }));
            zoneCameraId.value = cam;
            zoneZoneId.value = zone;
            updatePointCountUI();
            redrawCanvas();
            showToast(`Loaded zone '${zone}' onto canvas`, 'info');
          } catch (err) {
            showToast('Could not load polygon coordinates', 'error');
          }
        });

        // Run detection directly
        el.querySelector('.btn-zone-action-detect').addEventListener('click', async e => {
          const file = e.currentTarget.getAttribute('data-file');
          const cam = e.currentTarget.getAttribute('data-cam');
          const zone = e.currentTarget.getAttribute('data-zone');

          // Switch to Live Stream
          document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
          document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
          const streamTabBtn = document.querySelector('.tab-btn[data-tab="stream"]');
          if (streamTabBtn) streamTabBtn.classList.add('active');
          const tabStreamEl = document.getElementById('tab-stream');
          if (tabStreamEl) tabStreamEl.classList.add('active');

          activeMode = 'zone_intrusion';
          document.querySelectorAll('.mode-btn').forEach(b => {
            b.classList.toggle('active', b.getAttribute('data-mode') === 'zone_intrusion');
          });
          if (zoneConfigGroup) zoneConfigGroup.style.display = 'flex';

          if (sourceInput) sourceInput.value = captureSource.value.trim() || '0';
          if (cameraIdInput) cameraIdInput.value = cam;
          if (zoneIdInput) zoneIdInput.value = zone;

          await loadZonesForStream();
          if (streamZoneSelect && file) {
            streamZoneSelect.value = file;
          }

          setTimeout(() => {
            btnStreamStart.click();
          }, 300);
        });

        // Delete zone
        el.querySelector('.zone-delete-btn').addEventListener('click', async e => {
          const cam  = e.currentTarget.getAttribute('data-cam');
          const zone = e.currentTarget.getAttribute('data-zone');
          if (!confirm(`Delete zone '${zone}' on '${cam}'?`)) return;
          try {
            const dr = await fetch(`${getApiBase()}/zones/${encodeURIComponent(cam)}/${encodeURIComponent(zone)}`, {method: 'DELETE'});
            if (!dr.ok) throw new Error(`HTTP ${dr.status}`);
            showToast(`Zone '${zone}' deleted`, 'info');
            loadZonesList();
          } catch (err) {
            showToast(`Delete failed: ${err.message}`, 'error');
          }
        });

        zonesList.appendChild(el);
      });
    } catch (e) {
      zonesList.innerHTML = `<p style="font-size:12px;color:var(--color-false);">${e.message}</p>`;
    }
  }

  btnRefreshZones.addEventListener('click', loadZonesList);

  // =========================================================================
  // Alert feed controls
  // =========================================================================
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      e.currentTarget.classList.add('active');
      currentFilter = e.currentTarget.getAttribute('data-filter');
      renderAlertFeed();
    });
  });

  btnRefresh.addEventListener('click', () => { fetchAlerts(); fetchThresholds(); fetchPolicyHistory(); });
  btnSimPpe.addEventListener('click',  () => simulateEvent('ppe_violation'));
  btnSimZone.addEventListener('click', () => simulateEvent('zone_intrusion'));

  // =========================================================================
  // Control Panel (Subprocess Orchestration) Logic
  // =========================================================================
  let procPollTimer = null;
  const openLogsMap = new Set(); // tracks process names with expanded log viewers
  const lastKnownStatus = new Map();

  function formatTime(isoStr) {
    if (!isoStr) return '—';
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return isoStr;
    }
  }

  function updateProcessCardUI(proc) {
    const name = proc.name;
    const card = document.getElementById(`proc-card-${name}`);
    const dot = document.getElementById(`proc-dot-${name}`);
    const badge = document.getElementById(`proc-badge-${name}`);
    const btnStart = document.getElementById(`btn-start-${name}`);
    const btnStop = document.getElementById(`btn-stop-${name}`);
    const pidsEl = document.getElementById(`proc-pids-${name}`);
    const timeEl = document.getElementById(`proc-time-${name}`);
    const logCountEl = document.getElementById(`proc-logcount-${name}`);
    const pollInd = document.getElementById(`proc-poll-${name}`);
    const logBody = document.getElementById(`proc-logs-body-${name}`);
    const chevron = document.getElementById(`chevron-${name}`);

    if (!card) return;

    const prevStatus = lastKnownStatus.get(name);
    lastKnownStatus.set(name, proc.status);

    // If newly crashed, auto-open log viewer so the user sees error output immediately
    if (proc.status === 'crashed' && prevStatus !== 'crashed') {
      openLogsMap.add(name);
      if (logBody) logBody.classList.add('open');
      if (chevron) chevron.classList.add('rotated');
      fetchProcessLogs(name);
    }

    // Status classes
    card.classList.remove('is-running', 'is-crashed');
    if (proc.status === 'running') card.classList.add('is-running');
    if (proc.status === 'crashed') card.classList.add('is-crashed');

    // Dot & Badge styling
    if (dot) {
      dot.className = `proc-dot status-dot-${proc.status}`;
    }
    if (badge) {
      badge.className = `proc-badge badge-${proc.status}`;
      badge.textContent = proc.status.toUpperCase();
    }

    // Buttons
    if (btnStart) btnStart.disabled = (proc.status === 'running');
    if (btnStop) btnStop.disabled = (proc.status !== 'running');

    // Meta
    if (pidsEl) {
      pidsEl.textContent = (proc.pids && proc.pids.length > 0) ? proc.pids.join(', ') : '—';
    }
    if (timeEl) {
      timeEl.textContent = formatTime(proc.started_at);
    }
    if (logCountEl && typeof proc.logs_count === 'number') {
      logCountEl.textContent = proc.logs_count;
    }

    // Polling indicator
    if (pollInd) {
      pollInd.style.display = (proc.status === 'running' && openLogsMap.has(name)) ? 'flex' : 'none';
    }
  }

  async function loadProcessStatus() {
    try {
      const res = await fetch(`${getApiBase()}/processes`);
      if (!res.ok) return;
      const procs = await res.json();
      procs.forEach(p => {
        updateProcessCardUI(p);
        // If logs section is open or process is running, fetch latest logs
        if (openLogsMap.has(p.name) || p.status === 'running') {
          fetchProcessLogs(p.name);
        }
      });
    } catch (e) {
      console.warn('Failed to load process status:', e);
    }
  }

  async function fetchProcessLogs(name) {
    try {
      const res = await fetch(`${getApiBase()}/processes/${name}/logs?tail=500`);
      if (!res.ok) return;
      const data = await res.json();
      const pre = document.getElementById(`proc-logs-${name}`);
      const logBody = document.getElementById(`proc-logs-body-${name}`);
      const logCountEl = document.getElementById(`proc-logcount-${name}`);

      if (logCountEl && Array.isArray(data.logs)) {
        logCountEl.textContent = data.logs.length;
      }

      if (pre && Array.isArray(data.logs)) {
        const text = data.logs.length > 0 ? data.logs.join('\n') : '(No logs recorded)';
        // Check if user was already at bottom before appending to keep auto-scrolling
        const isNearBottom = logBody ? (logBody.scrollHeight - logBody.scrollTop - logBody.clientHeight < 60) : false;
        pre.textContent = text;
        if (isNearBottom && logBody) {
          logBody.scrollTop = logBody.scrollHeight;
        }
      }
    } catch (e) {
      console.warn(`Failed to fetch logs for ${name}:`, e);
    }
  }

  function startProcessPolling() {
    if (procPollTimer) clearInterval(procPollTimer);
    procPollTimer = setInterval(loadProcessStatus, 1500);
  }

  function stopProcessPolling() {
    if (procPollTimer) {
      clearInterval(procPollTimer);
      procPollTimer = null;
    }
  }

  // Bind Start buttons
  document.querySelectorAll('.btn-proc-start').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.getAttribute('data-proc');
      if (!name) return;

      btn.disabled = true;
      let bodyData = null;

      if (name === 'zone_pipeline') {
        const srcInput = document.getElementById('zone-proc-source');
        const sourceVal = srcInput ? srcInput.value.trim() : 'demo/videos/zone_intrusion_demo.mp4';
        bodyData = JSON.stringify({ source: sourceVal });
      }

      try {
        const res = await fetch(`${getApiBase()}/processes/${name}/start`, {
          method: 'POST',
          headers: bodyData ? { 'Content-Type': 'application/json' } : {},
          body: bodyData,
        });

        if (!res.ok) {
          const err = await res.json();
          showToast(`Start failed: ${err.detail || res.statusText}`, 'error');
          btn.disabled = false;
          return;
        }

        const data = await res.json();
        updateProcessCardUI(data);

        // Auto-open logs panel so operator sees immediate progress
        openLogsMap.add(name);
        const logBody = document.getElementById(`proc-logs-body-${name}`);
        const chevron = document.getElementById(`chevron-${name}`);
        if (logBody) logBody.classList.add('open');
        if (chevron) chevron.classList.add('rotated');

        showToast(`Process ${name} launched`, 'info');
        loadProcessStatus();
      } catch (e) {
        showToast(`Error starting process: ${e.message}`, 'error');
        btn.disabled = false;
      }
    });
  });

  // Bind Stop buttons
  document.querySelectorAll('.btn-proc-stop').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.getAttribute('data-proc');
      if (!name) return;

      btn.disabled = true;
      try {
        const res = await fetch(`${getApiBase()}/processes/${name}/stop`, {
          method: 'POST',
        });
        if (!res.ok) {
          const err = await res.json();
          showToast(`Stop failed: ${err.detail || res.statusText}`, 'error');
          btn.disabled = false;
          return;
        }
        const data = await res.json();
        updateProcessCardUI(data);
        showToast(`Process ${name} stopped`, 'info');
        loadProcessStatus();
      } catch (e) {
        showToast(`Error stopping process: ${e.message}`, 'error');
        btn.disabled = false;
      }
    });
  });

  // Bind Log Toggle buttons
  document.querySelectorAll('.btn-toggle-logs').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.getAttribute('data-proc');
      if (!name) return;
      const logBody = document.getElementById(`proc-logs-body-${name}`);
      const chevron = document.getElementById(`chevron-${name}`);

      if (!logBody) return;
      if (logBody.classList.contains('open')) {
        logBody.classList.remove('open');
        if (chevron) chevron.classList.remove('rotated');
        openLogsMap.delete(name);
      } else {
        logBody.classList.add('open');
        if (chevron) chevron.classList.add('rotated');
        openLogsMap.add(name);
        fetchProcessLogs(name);
        // Scroll to bottom on open
        setTimeout(() => { logBody.scrollTop = logBody.scrollHeight; }, 50);
      }
      loadProcessStatus();
    });
  });

  // Bind Copy Log buttons
  document.querySelectorAll('.btn-copy-logs').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.getAttribute('data-proc');
      if (!name) return;
      const pre = document.getElementById(`proc-logs-${name}`);
      if (pre && pre.textContent) {
        navigator.clipboard.writeText(pre.textContent).then(() => {
          showToast(`Copied ${name} logs to clipboard`, 'info');
        }).catch(() => {
          showToast('Failed to copy to clipboard', 'error');
        });
      }
    });
  });

  // Sync Zone Source Dropdown & Input
  const zoneSourceSelect = document.getElementById('zone-proc-source-select');
  const zoneSourceInput = document.getElementById('zone-proc-source');
  if (zoneSourceSelect && zoneSourceInput) {
    zoneSourceSelect.addEventListener('change', () => {
      if (zoneSourceSelect.value === 'custom') {
        zoneSourceInput.focus();
      } else {
        zoneSourceInput.value = zoneSourceSelect.value;
      }
    });
  }

  // Refresh process list button
  const btnRefreshProcs = document.getElementById('btn-refresh-procs');
  if (btnRefreshProcs) {
    btnRefreshProcs.addEventListener('click', loadProcessStatus);
  }

  // Initial process status check
  loadProcessStatus();

  // =========================================================================
  // Polling loop
  // =========================================================================
  fetchAlerts();
  fetchThresholds();
  fetchPolicyHistory();
  setInterval(() => { fetchAlerts(); fetchThresholds(); }, 2000);
});


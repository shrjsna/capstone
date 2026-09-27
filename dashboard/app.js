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
  const host = window.location.hostname; // e.g. "127.0.0.1" or "192.168.1.42"
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
  const btnCapture     = document.getElementById('btn-capture-frame');
  const zoneCameraId   = document.getElementById('zone-camera-id');
  const zoneZoneId     = document.getElementById('zone-zone-id');
  const zoneCanvas     = document.getElementById('zone-canvas');
  const canvasContainer = document.getElementById('canvas-container');
  const canvasPlaceholder = document.getElementById('canvas-placeholder');
  const btnZoneUndo    = document.getElementById('btn-zone-undo');
  const btnZoneClear   = document.getElementById('btn-zone-clear');
  const btnZoneSave    = document.getElementById('btn-zone-save');
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
  let streamCameraId   = 'stream_cam_01';  // tracks the camera_id used for current stream

  // Zone draw state
  let zonePoints       = [];            // [{x,y}] canvas-coordinate polygon points
  let capturedImageData = null;         // ImageData or img element for background
  let canvasCtx        = null;

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

  btnCapture.addEventListener('click', async () => {
    const src = captureSource.value.trim();
    if (!src) { showToast('Enter a source.', 'error'); return; }

    btnCapture.disabled = true;
    btnCapture.textContent = 'Capturing…';

    try {
      const r = await fetch(`${getApiBase()}/capture-frame?source=${encodeURIComponent(src)}`);
      if (!r.ok) {
        const err = await r.json().catch(() => ({detail: `HTTP ${r.status}`}));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }

      const frameWidth  = r.headers.get('X-Frame-Width');
      const frameHeight = r.headers.get('X-Frame-Height');

      const blob = await r.blob();
      const imgUrl = URL.createObjectURL(blob);
      const img = new Image();
      img.onload = () => {
        // Fit canvas inside the container, preserving aspect ratio
        const containerW = canvasContainer.clientWidth - 2;
        const containerH = canvasContainer.clientHeight - 2;
        const scale = Math.min(containerW / img.width, containerH / img.height, 1);
        zoneCanvas.width  = Math.round(img.width  * scale);
        zoneCanvas.height = Math.round(img.height * scale);
        zoneCanvas._imgElement = img;
        zoneCanvas._scale = scale;
        zoneCanvas._naturalW = img.width;
        zoneCanvas._naturalH = img.height;

        canvasPlaceholder.style.display = 'none';
        zoneCanvas.style.display = 'block';

        // Clear polygon when a new frame is captured
        zonePoints = [];
        updatePointCountUI();
        redrawCanvas();
        showToast('Frame captured — click to add polygon points', 'info');
      };
      img.onerror = () => { throw new Error('Could not decode captured image.'); };
      img.src = imgUrl;
    } catch (e) {
      showToast(`Capture failed: ${e.message}`, 'error');
    } finally {
      btnCapture.disabled = false;
      btnCapture.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>Capture Frame`;
    }
  });

  zoneCanvas.addEventListener('click', e => {
    if (!zoneCanvas._imgElement) return;
    const rect = zoneCanvas.getBoundingClientRect();
    const x = Math.round(e.clientX - rect.left);
    const y = Math.round(e.clientY - rect.top);
    zonePoints.push({x, y});
    updatePointCountUI();
    redrawCanvas();
  });

  function redrawCanvas() {
    if (!canvasCtx || !zoneCanvas._imgElement) return;
    const ctx = canvasCtx;
    ctx.clearRect(0, 0, zoneCanvas.width, zoneCanvas.height);

    // Draw background image
    ctx.drawImage(zoneCanvas._imgElement, 0, 0, zoneCanvas.width, zoneCanvas.height);

    if (zonePoints.length === 0) return;

    // Fill semi-transparent polygon
    if (zonePoints.length >= 3) {
      ctx.beginPath();
      ctx.moveTo(zonePoints[0].x, zonePoints[0].y);
      zonePoints.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
      ctx.closePath();
      ctx.fillStyle = 'rgba(56, 189, 248, 0.15)';
      ctx.fill();
    }

    // Draw edges
    ctx.beginPath();
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 2;
    ctx.setLineDash([]);
    ctx.moveTo(zonePoints[0].x, zonePoints[0].y);
    zonePoints.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
    if (zonePoints.length >= 3) {
      ctx.setLineDash([5, 4]);
      ctx.lineTo(zonePoints[0].x, zonePoints[0].y);  // closing edge preview dashed
      ctx.setLineDash([]);
    }
    ctx.stroke();

    // Draw vertices
    zonePoints.forEach((p, i) => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
      ctx.fillStyle = i === 0 ? '#10b981' : '#38bdf8';
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      // Index label
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 11px Inter, sans-serif';
      ctx.fillText(i + 1, p.x + 7, p.y - 5);
    });
  }

  function updatePointCountUI() {
    pointCount.textContent = zonePoints.length;
    btnZoneUndo.disabled = zonePoints.length === 0;
    btnZoneClear.disabled = zonePoints.length === 0;
    btnZoneSave.disabled = zonePoints.length < 3;
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

  btnZoneSave.addEventListener('click', async () => {
    if (zonePoints.length < 3) return;
    const camId  = zoneCameraId.value.trim() || 'cam_01';
    const zoneId = zoneZoneId.value.trim()   || 'zone_1';
    const scale  = zoneCanvas._scale || 1;

    // Convert canvas coordinates back to native pixel coordinates
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
    } catch (e) {
      zoneSaveResult.style.display = 'block';
      zoneSaveResult.className = 'zone-save-result error';
      zoneSaveResult.textContent = `Save failed: ${e.message}`;
    }
  });

  // =========================================================================
  // Zone list
  // =========================================================================
  async function loadZonesList() {
    try {
      const r = await fetch(`${getApiBase()}/zones`);
      if (!r.ok) { zonesList.innerHTML = '<p style="font-size:12px;color:var(--text-dim);">Could not load zones.</p>'; return; }
      const zones = await r.json();
      zonesList.innerHTML = '';
      if (zones.length === 0) {
        zonesList.innerHTML = '<p style="font-size:12px;color:var(--text-dim);">No saved zones yet. Draw one above.</p>';
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
          <button class="btn-icon zone-delete-btn" title="Delete zone" data-cam="${z.camera_id}" data-zone="${z.zone_id}">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
            </svg>
          </button>`;
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
  // Polling loop
  // =========================================================================
  fetchAlerts();
  fetchThresholds();
  fetchPolicyHistory();
  setInterval(() => { fetchAlerts(); fetchThresholds(); }, 2000);
});

/**
 * AEGIS Operations Console — Dark Editorial FX Engine (fx.js)
 * 
 * Interactive Wireframe Tunnel + Draggable Physics Tags + MutationObserver Stats
 * Offline-ready, zero-network, scoped strictly to dashboard presentation.
 */

(() => {
  'use strict';

  document.addEventListener('DOMContentLoaded', () => {
    initHeroTunnel();
    initHeroStatsObservers();
  });

  // =========================================================================
  // 1. Interactive Wireframe Tunnel & Physics Tag Field
  // =========================================================================
  function initHeroTunnel() {
    const hero = document.querySelector('.fx-hero');
    const tunnelContainer = document.getElementById('fx-tunnel-container');
    const tunnelSvg = document.getElementById('fx-tunnel-svg');
    const spokesGroup = document.getElementById('fx-tunnel-spokes');
    const rectsGroup = document.getElementById('fx-tunnel-rects');
    const dotsGroup = document.getElementById('fx-tunnel-dots');
    const coreCircle = document.getElementById('fx-tunnel-core');
    const openAlertsBtn = document.getElementById('fx-btn-open-alerts');
    const tagElements = document.querySelectorAll('.fx-tag-pill');
    const alertsTab = document.getElementById('tab-alerts');

    if (!hero || !tunnelContainer || !tunnelSvg) return;

    // Smooth scroll from "Open Alerts" button
    openAlertsBtn?.addEventListener('click', (e) => {
      e.preventDefault();
      const feedPanel = document.querySelector('.feed-panel');
      if (feedPanel) {
        feedPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });

    // -----------------------------------------------------------------------
    // Tunnel Geometry & Spring Vanishing Point
    // -----------------------------------------------------------------------
    const SVG_W = 400;
    const SVG_H = 320;
    const NUM_RECTS = 22;

    let cx = SVG_W / 2;
    let cy = SVG_H / 2;
    let targetX = cx;
    let targetY = cy;
    let isPointerOver = false;

    // Build static SVG elements once for 22 rects, spokes, and dots
    const rectEls = [];
    rectsGroup.innerHTML = '';
    for (let i = 0; i < NUM_RECTS; i++) {
      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      // Hairline strokes; inner rects carry subtle accent tint
      const t = i / (NUM_RECTS - 1);
      const strokeColor = i % 4 === 0 
        ? `rgba(255, 106, 0, ${0.28 + (1 - t) * 0.45})` 
        : `rgba(241, 230, 226, ${0.16 + (1 - t) * 0.42})`;
      rect.setAttribute('stroke', strokeColor);
      rect.setAttribute('stroke-width', '1');
      rect.setAttribute('fill', 'none');
      rectsGroup.appendChild(rect);
      rectEls.push(rect);
    }

    // Radial anchor points around outer perimeter for spokes
    const spokeAnchors = [
      [0, 0], [SVG_W / 3, 0], [(2 * SVG_W) / 3, 0], [SVG_W, 0],
      [SVG_W, SVG_H / 3], [SVG_W, (2 * SVG_H) / 3], [SVG_W, SVG_H],
      [(2 * SVG_W) / 3, SVG_H], [SVG_W / 3, SVG_H], [0, SVG_H],
      [0, (2 * SVG_H) / 3], [0, SVG_H / 3]
    ];
    const spokeEls = [];
    spokesGroup.innerHTML = '';
    for (let i = 0; i < spokeAnchors.length; i++) {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('stroke', 'rgba(241, 230, 226, 0.18)');
      line.setAttribute('stroke-width', '1');
      line.setAttribute('x2', spokeAnchors[i][0]);
      line.setAttribute('y2', spokeAnchors[i][1]);
      spokesGroup.appendChild(line);
      spokeEls.push(line);
    }

    // Dots along selected key frames
    const dotIndices = [2, 6, 11, 16, 20];
    const dotEls = [];
    dotsGroup.innerHTML = '';
    dotIndices.forEach(() => {
      for (let j = 0; j < 4; j++) {
        const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        dot.setAttribute('r', '2.2');
        dot.setAttribute('fill', '#ff6a00');
        dotsGroup.appendChild(dot);
        dotEls.push(dot);
      }
    });

    // Pointer events on tunnel and hero for vanishing point tracking
    function handlePointerCoord(clientX, clientY) {
      const rect = tunnelContainer.getBoundingClientRect();
      const relX = clientX - (rect.left + rect.width / 2);
      const relY = clientY - (rect.top + rect.height / 2);
      const clampedX = Math.max(-85, Math.min(85, (relX / (rect.width / 2)) * 80));
      const clampedY = Math.max(-65, Math.min(65, (relY / (rect.height / 2)) * 60));
      targetX = SVG_W / 2 + clampedX;
      targetY = SVG_H / 2 + clampedY;
    }

    hero.addEventListener('pointermove', (e) => {
      isPointerOver = true;
      handlePointerCoord(e.clientX, e.clientY);
    });

    hero.addEventListener('pointerleave', () => {
      isPointerOver = false;
      targetX = SVG_W / 2;
      targetY = SVG_H / 2;
    });

    // Device orientation tilt support
    if (window.DeviceOrientationEvent) {
      window.addEventListener('deviceorientation', (e) => {
        if (e.gamma !== null && e.beta !== null && !isPointerOver) {
          const tiltX = Math.max(-60, Math.min(60, (e.gamma / 45) * 60));
          const tiltY = Math.max(-45, Math.min(45, ((e.beta - 45) / 45) * 45));
          targetX = SVG_W / 2 + tiltX;
          targetY = SVG_H / 2 + tiltY;
        }
      }, { passive: true });
    }

    // Render tunnel frame
    function updateTunnel() {
      // Spring easing towards target
      cx += (targetX - cx) * 0.085;
      cy += (targetY - cy) * 0.085;

      // Update concentric rectangles
      let dotCounter = 0;
      for (let i = 0; i < NUM_RECTS; i++) {
        // Perspective scaling function
        const progress = i / (NUM_RECTS - 1);
        const s = Math.pow(1 - progress, 1.45);
        const x1 = cx + (0 - cx) * s;
        const y1 = cy + (0 - cy) * s;
        const x2 = cx + (SVG_W - cx) * s;
        const y2 = cy + (SVG_H - cy) * s;
        const w = Math.max(0, x2 - x1);
        const h = Math.max(0, y2 - y1);

        const rEl = rectEls[i];
        rEl.setAttribute('x', x1.toFixed(1));
        rEl.setAttribute('y', y1.toFixed(1));
        rEl.setAttribute('width', w.toFixed(1));
        rEl.setAttribute('height', h.toFixed(1));

        if (dotIndices.includes(i)) {
          // 4 corner dots
          const pts = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]];
          for (let p = 0; p < 4; p++) {
            if (dotEls[dotCounter]) {
              dotEls[dotCounter].setAttribute('cx', pts[p][0].toFixed(1));
              dotEls[dotCounter].setAttribute('cy', pts[p][1].toFixed(1));
              dotCounter++;
            }
          }
        }
      }

      // Update radial spokes
      for (let i = 0; i < spokeEls.length; i++) {
        spokeEls[i].setAttribute('x1', cx.toFixed(1));
        spokeEls[i].setAttribute('y1', cy.toFixed(1));
      }

      // Update dark core circle
      if (coreCircle) {
        coreCircle.setAttribute('cx', cx.toFixed(1));
        coreCircle.setAttribute('cy', cy.toFixed(1));
      }
    }

    // -----------------------------------------------------------------------
    // 2. Draggable Physics Tag Engine
    // -----------------------------------------------------------------------
    const GRAVITY = 0.32;
    const AIR_RESISTANCE = 0.985;
    const WALL_RESTITUTION = 0.65;
    const FLOOR_RESTITUTION = 0.48;
    const FLOOR_FRICTION = 0.82;

    const tags = [];

    // Initialize tag objects
    tagElements.forEach((el, index) => {
      // Alternating editorial tilts
      const baseTilt = (index % 2 === 0 ? -1 : 1) * (1.5 + (index % 3) * 0.8);
      tags.push({
        el,
        x: 0,
        y: 0,
        vx: 0,
        vy: 0,
        w: 0,
        h: 0,
        isDragging: false,
        isPinned: false,
        pinRelX: 0,
        pinRelY: 0,
        tilt: baseTilt,
        lastPX: 0,
        lastPY: 0,
        lastPT: 0
      });
    });

    // Position tags initially along tags row
    function resetTagPositions() {
      const heroRect = hero.getBoundingClientRect();
      const tagsContainer = document.getElementById('fx-tags-field');
      const startRect = tagsContainer ? tagsContainer.getBoundingClientRect() : heroRect;
      let curX = Math.max(12, startRect.left - heroRect.left);
      let curY = Math.max(12, startRect.top - heroRect.top);

      tags.forEach((tag, idx) => {
        const elRect = tag.el.getBoundingClientRect();
        tag.w = elRect.width || 80;
        tag.h = elRect.height || 28;

        if (!tag.isPinned && !tag.isDragging) {
          tag.x = curX;
          tag.y = curY;
          tag.vx = (Math.random() - 0.5) * 1.5;
          tag.vy = 0;

          curX += tag.w + 10;
          if (curX + tag.w > heroRect.width - (window.innerWidth > 768 ? 390 : 20)) {
            curX = Math.max(12, startRect.left - heroRect.left);
            curY += tag.h + 8;
          }
        }
      });
    }

    // Set up dragging listeners on each tag
    tags.forEach((tag) => {
      const el = tag.el;
      el.style.touchAction = 'none';

      el.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        el.setPointerCapture(e.pointerId);

        tag.isDragging = true;
        tag.lastPX = e.clientX;
        tag.lastPY = e.clientY;
        tag.lastPT = performance.now();
        tag.vx = 0;
        tag.vy = 0;

        // If previously pinned, picking up releases it
        if (tag.isPinned) {
          tag.isPinned = false;
          el.classList.remove('fx-pinned');
        }

        el.classList.add('fx-dragging');
      });

      el.addEventListener('pointermove', (e) => {
        if (!tag.isDragging) return;
        const now = performance.now();
        const dt = Math.max(1, now - tag.lastPT);
        const dx = e.clientX - tag.lastPX;
        const dy = e.clientY - tag.lastPY;

        tag.x += dx;
        tag.y += dy;

        // Calculate throwing momentum
        tag.vx = (dx / dt) * 14;
        tag.vy = (dy / dt) * 14;

        tag.lastPX = e.clientX;
        tag.lastPY = e.clientY;
        tag.lastPT = now;

        el.style.transform = `translate3d(${tag.x}px, ${tag.y}px, 0) rotate(${tag.tilt * 1.5}deg) scale(1.06)`;
      });

      const handlePointerEnd = (e) => {
        if (!tag.isDragging) return;
        try {
          el.releasePointerCapture(e.pointerId);
        } catch (_) {}

        tag.isDragging = false;
        el.classList.remove('fx-dragging');

        // Check if released over tunnel box
        const heroRect = hero.getBoundingClientRect();
        const tunnelRect = tunnelContainer.getBoundingClientRect();
        const tagCenterX = heroRect.left + tag.x + tag.w / 2;
        const tagCenterY = heroRect.top + tag.y + tag.h / 2;

        const overTunnel = (
          tagCenterX >= tunnelRect.left &&
          tagCenterX <= tunnelRect.right &&
          tagCenterY >= tunnelRect.top &&
          tagCenterY <= tunnelRect.bottom
        );

        if (overTunnel) {
          // PIN TAG ON TUNNEL
          tag.isPinned = true;
          tag.vx = 0;
          tag.vy = 0;
          tag.pinRelX = tagCenterX - tunnelRect.left;
          tag.pinRelY = tagCenterY - tunnelRect.top;
          el.classList.add('fx-pinned');
        } else {
          // Cap throwing velocity
          tag.vx = Math.max(-18, Math.min(18, tag.vx));
          tag.vy = Math.max(-18, Math.min(18, tag.vy));
        }
      };

      el.addEventListener('pointerup', handlePointerEnd);
      el.addEventListener('pointercancel', handlePointerEnd);
    });

    // Compute floor bounds based on viewport
    function getFloorY(heroRect) {
      if (window.innerWidth <= 768) {
        const leftCell = document.querySelector('.fx-hero-left');
        if (leftCell) {
          const leftRect = leftCell.getBoundingClientRect();
          return (leftRect.bottom - heroRect.top) - 10;
        }
      }
      return heroRect.height - 12;
    }

    // Step physics forward
    function updatePhysics() {
      const heroRect = hero.getBoundingClientRect();
      const tunnelRect = tunnelContainer.getBoundingClientRect();
      const floorY = getFloorY(heroRect);
      const rightWall = heroRect.width - 10;

      for (let i = 0; i < tags.length; i++) {
        const tag = tags[i];
        if (tag.isDragging) continue;

        if (tag.isPinned) {
          // Parallax shift with tunnel perspective
          const parallaxX = ((cx - SVG_W / 2) / (SVG_W / 2)) * 14;
          const parallaxY = ((cy - SVG_H / 2) / (SVG_H / 2)) * 10;
          tag.x = (tunnelRect.left - heroRect.left) + tag.pinRelX - tag.w / 2 + parallaxX;
          tag.y = (tunnelRect.top - heroRect.top) + tag.pinRelY - tag.h / 2 + parallaxY;

          tag.el.style.transform = `translate3d(${tag.x.toFixed(1)}px, ${tag.y.toFixed(1)}px, 0) rotate(${tag.tilt}deg)`;
          continue;
        }

        // Apply forces
        tag.vy += GRAVITY;
        tag.vx *= AIR_RESISTANCE;
        tag.vy *= AIR_RESISTANCE;

        tag.x += tag.vx;
        tag.y += tag.vy;

        // Floor collision
        if (tag.y + tag.h >= floorY) {
          tag.y = floorY - tag.h;
          tag.vy = -tag.vy * FLOOR_RESTITUTION;
          tag.vx *= FLOOR_FRICTION;
          if (Math.abs(tag.vy) < 0.28) tag.vy = 0;
        }

        // Ceiling
        if (tag.y < 4) {
          tag.y = 4;
          tag.vy = -tag.vy * 0.5;
        }

        // Left / Right walls
        if (tag.x < 6) {
          tag.x = 6;
          tag.vx = -tag.vx * WALL_RESTITUTION;
        } else if (tag.x + tag.w > rightWall) {
          tag.x = rightWall - tag.w;
          tag.vx = -tag.vx * WALL_RESTITUTION;
        }

        // Light pairwise collision separation
        for (let j = i + 1; j < tags.length; j++) {
          const other = tags[j];
          if (other.isDragging || other.isPinned) continue;

          const dx = (tag.x + tag.w / 2) - (other.x + other.w / 2);
          const dy = (tag.y + tag.h / 2) - (other.y + other.h / 2);
          const minDistX = (tag.w + other.w) * 0.48;
          const minDistY = (tag.h + other.h) * 0.48;

          if (Math.abs(dx) < minDistX && Math.abs(dy) < minDistY) {
            const overlapX = minDistX - Math.abs(dx);
            const overlapY = minDistY - Math.abs(dy);

            if (overlapX < overlapY) {
              const sign = dx > 0 ? 1 : -1;
              tag.x += sign * overlapX * 0.35;
              other.x -= sign * overlapX * 0.35;
              const vAvg = (tag.vx + other.vx) * 0.5;
              tag.vx = vAvg + sign * 0.5;
              other.vx = vAvg - sign * 0.5;
            } else {
              const sign = dy > 0 ? 1 : -1;
              tag.y += sign * overlapY * 0.35;
              other.y -= sign * overlapY * 0.35;
              const vAvg = (tag.vy + other.vy) * 0.5;
              tag.vy = vAvg + sign * 0.4;
              other.vy = vAvg - sign * 0.4;
            }
          }
        }

        tag.el.style.transform = `translate3d(${tag.x.toFixed(1)}px, ${tag.y.toFixed(1)}px, 0) rotate(${tag.tilt}deg)`;
      }
    }

    // Initial positioning after DOM layout settles
    window.addEventListener('load', resetTagPositions);
    window.addEventListener('resize', resetTagPositions);
    setTimeout(resetTagPositions, 150);

    // -----------------------------------------------------------------------
    // 3. Main Animation Loop (rAF with pause when inactive)
    // -----------------------------------------------------------------------
    let animId = null;

    function renderLoop() {
      // Pause loop if #tab-alerts is not active or document is hidden
      const isAlertsActive = alertsTab && alertsTab.classList.contains('active');
      const isVisible = !document.hidden;

      if (isAlertsActive && isVisible) {
        updateTunnel();
        updatePhysics();
      }

      animId = requestAnimationFrame(renderLoop);
    }

    animId = requestAnimationFrame(renderLoop);

    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && (!animId || animId === null)) {
        animId = requestAnimationFrame(renderLoop);
      }
    });
  }

  // =========================================================================
  // 2. Hero Stats Strip MutationObservers
  // =========================================================================
  function initHeroStatsObservers() {
    const statShown = document.getElementById('fx-stat-shown');
    const statUnreviewed = document.getElementById('fx-stat-unreviewed');
    const statPolicy = document.getElementById('fx-stat-policy');

    const alertCountBadge = document.getElementById('alert-count-badge');
    const headerPolicy = document.getElementById('header-policy-ver');
    const feedContainer = document.getElementById('alert-feed-container');

    // Sync functions
    function syncAlertsShown() {
      if (!statShown || !alertCountBadge) return;
      const text = alertCountBadge.textContent || '';
      const match = text.match(/\d+/);
      statShown.textContent = match ? match[0] : '0';
    }

    function syncPolicyVer() {
      if (!statPolicy || !headerPolicy) return;
      statPolicy.textContent = (headerPolicy.textContent || '').trim() || 'v1.0.0';
    }

    function syncUnreviewed() {
      if (!statUnreviewed || !feedContainer) return;
      // Unreviewed cards are those that still present the .btn-confirm action button
      const unreviewedCards = feedContainer.querySelectorAll('.alert-card .btn-confirm');
      statUnreviewed.textContent = String(unreviewedCards.length);
    }

    // Initial read
    syncAlertsShown();
    syncPolicyVer();
    syncUnreviewed();

    // Observer 1: Alert Count Badge
    if (alertCountBadge) {
      const badgeObs = new MutationObserver(() => syncAlertsShown());
      badgeObs.observe(alertCountBadge, { childList: true, characterData: true, subtree: true });
    }

    // Observer 2: Policy Version Pill
    if (headerPolicy) {
      const policyObs = new MutationObserver(() => syncPolicyVer());
      policyObs.observe(headerPolicy, { childList: true, characterData: true, subtree: true });
    }

    // Observer 3: Feed Container for unreviewed count
    if (feedContainer) {
      const feedObs = new MutationObserver(() => syncUnreviewed());
      feedObs.observe(feedContainer, { childList: true, subtree: true });
    }
  }

})();


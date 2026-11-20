# styles.css Detailed Diff Report

## 1. :root Tokens Comparison

| Variable | Current Value | Backup Value | Status |
|---|---|---|---|
| `--accent` | `#ff6a00` | `#FF6A00` | **CHANGED** |
| `--accent-hover` | `#ff8533` | `#FF8533` | **CHANGED** |
| `--accent-press` | `#e65f00` | `#E65F00` | **CHANGED** |
| `--bg-card` | `var(--surface)` | `var(--surface)` | Unchanged |
| `--bg-card-hover` | `var(--surface-2)` | `var(--surface-2)` | Unchanged |
| `--bg-dark` | `—` | `var(--bg)` | **REMOVED** |
| `--bg-surface` | `var(--surface)` | `var(--surface)` | Unchanged |
| `--border` | `rgba(241, 230, 226, 0.38)` | `#2E2E2E` | **CHANGED** |
| `--border-highlight` | `var(--border)` | `var(--border)` | Unchanged |
| `--border-subtle` | `var(--border)` | `var(--border)` | Unchanged |
| `--danger` | `#ff5a5a` | `—` | **ADDED** |
| `--font-body` | `var(--font-sans)` | `'Inter', sans-serif` | **CHANGED** |
| `--font-heading` | `var(--font-display)` | `'Outfit', sans-serif` | **CHANGED** |
| `--font-mono` | `'JetBrains Mono', 'SF Mono', Consolas, monospace` | `—` | **ADDED** |
| `--font-sans` | `'Inter', -apple-system, BlinkMacSystemFont, '...` | `—` | **ADDED** |
| `--on-accent` | `#1c1918` | `#0A0A0A` | **CHANGED** |
| `--radius-lg` | `0px` | `14px` | **CHANGED** |
| `--radius-md` | `0px` | `10px` | **CHANGED** |
| `--radius-pill` | `9999px` | `—` | **ADDED** |
| `--radius-sm` | `—` | `6px` | **REMOVED** |
| `--surface` | `#221e1d` | `#141414` | **CHANGED** |
| `--surface-2` | `#2b2625` | `#1E1E1E` | **CHANGED** |
| `--text` | `#f1e6e2` | `#FFFFFF` | **CHANGED** |
| `--text-dim` | `var(--text-muted)` | `var(--text-muted)` | Unchanged |
| `--text-main` | `var(--text)` | `var(--text)` | Unchanged |
| `--text-muted` | `#b3a8a4` | `#A3A3A3` | **CHANGED** |
| `--warning` | `#ff9800` | `—` | **ADDED** |

## 2. Added Selectors (125)

- `#fx-tunnel-svg`
- `*, *::before, *::after`
- `.alert-banner`
- `.audit-denied-cell`
- `.btn-demo.ppe`
- `.btn-demo.zone`
- `.btn-primary, .btn-demo, .btn-proc-start, .btn-detect-zone-action`
- `.btn-primary:active:not(:disabled), .btn-demo:active:not(:disabled), .btn-proc-start:active:not(:disabled), .btn-detect-zone-action:active:not(:disabled)`
- `.btn-primary:disabled, .btn-proc-start:disabled, .btn-detect-zone-action:disabled`
- `.btn-primary:hover:not(:disabled), .btn-demo:hover:not(:disabled), .btn-proc-start:hover:not(:disabled), .btn-detect-zone-action:hover:not(:disabled)`
- `.btn-secondary:disabled, .btn-proc-stop:disabled`
- `.btn-secondary:hover:not(:disabled), .btn-proc-stop:hover:not(:disabled), .btn-icon:hover:not(:disabled), .btn-table-action:hover:not(:disabled), .btn-copy-logs:hover:not(:disabled)`
- `.btn-table-action.danger`
- `.canvas-container`
- `.canvas-placeholder svg`
- `.console-grid .fx-title-band`
- `.console-grid, .stream-layout, .zone-layout, .control-layout`
- `.data-table tbody td`
- `.data-table tbody tr:hover td`
- `.data-table thead th`
- `.dot`
- `.dot.offline`
- `.feed-empty-state h3, .feed-error-state h3`
- `.feed-empty-state p, .feed-error-state p`
- `.filter-btn:hover`
- `.filter-btn:last-child`
- `.form-group`
- `.form-input:focus, .filter-select:focus, .filter-search-input:focus`
- `.fx-btn-open-alerts`
- `.fx-frame`
- `.fx-hero`
- `.fx-hero-actions`
- `.fx-hero-hint`
- `.fx-hero-hint::before`
- `.fx-hero-left`
- `.fx-hero-slash`
- `.fx-hero-sub`
- `.fx-hero-title`
- `.fx-hero-title-box`
- `.fx-hero-tunnel-wrap`
- `.fx-hero:hover .fx-slash-line-1::before, .fx-hero:hover .fx-slash-line-2::before`
- `.fx-slash-accent`
- `.fx-slash-accent::before`
- `.fx-slash-line-1::before`
- `.fx-slash-line-2::before`
- `.fx-stat-cell`
- `.fx-stat-label`
- `.fx-stat-val`
- `.fx-stats-strip`
- `.fx-tag-pill`
- `.fx-tag-pill.fx-dragging`
- `.fx-tag-pill.fx-pinned`
- `.fx-tag-pill:hover`
- `.fx-title-band:hover .fx-slash-accent::before, .fx-slash-accent:hover::before`
- `.fx-title-text`
- `.fx-title-wrap`
- `.fx-tunnel-canvas-box`
- `.fx-tunnel-header`
- `.fx-tunnel-label`
- `.fx-tunnel-status`
- *... and 65 more*

## 3. Removed Selectors (115)

- `*`
- `.alert-filter-bar`
- `.backend-url-selector`
- `.backend-url-selector input`
- `.backend-url-selector input:focus`
- `.btn-demo`
- `.btn-demo.ppe:hover`
- `.btn-demo.zone:hover`
- `.btn-detect-zone-action`
- `.btn-detect-zone-action:hover:not(:disabled)`
- `.btn-icon`
- `.btn-icon:hover`
- `.btn-primary`
- `.btn-primary:disabled`
- `.btn-primary:hover`
- `.btn-proc-start, .btn-proc-stop`
- `.btn-secondary`
- `.btn-secondary:disabled`
- `.btn-secondary:hover`
- `.btn-table-action`
- `.btn-table-action:hover`
- `.control-grid`
- `.counter-pill`
- `.data-table td`
- `.data-table th`
- `.data-table tr:hover td`
- `.demo-box`
- `.dot-small`
- `.feed-controls`
- `.feed-empty-state`
- `.feed-error-state`
- `.feedback-status-badge`
- `.filter-label`
- `.filter-search-input`
- `.filter-search-input:focus`
- `.filter-select`
- `.filter-select:focus`
- `.form-advanced summary`
- `.form-input`
- `.form-input:focus`
- `.history-list`
- `.info-key`
- `.info-row`
- `.info-val`
- `.inline-code`
- `.log-poll-indicator`
- `.logs-actions`
- `.margin-top`
- `.offline-dot`
- `.panel-header h2, .panel-header h3`
- `.phone-note`
- `.phone-note code`
- `.proc-actions button`
- `.proc-badge`
- `.proc-config-row`
- `.proc-logs-body`
- `.proc-meta-item`
- `.process-card:hover`
- `.role-badge`
- `.seg-btn:not(.active):hover`
- *... and 55 more*

## 4. Media Queries Comparison

### Backup Media Queries:
- `@media (max-width: 900px) {`
- `@media (max-width: 1024px) {`
- `@media (max-width: 768px) {`
- `@media (max-width: 480px) {`

### Current Media Queries:
- `@media (max-width: 1024px) {`
- `@media (max-width: 900px) {`
- `@media (max-width: 768px) {`
- `@media (max-width: 480px) {`
- `@media (prefers-reduced-motion: reduce) {`

## 5. Critical Property Rules (display, overflow, pointer-events, z-index, !important)

| Selector | Critical Properties Found | Declarations |
|---|---|---|
| `/* AEGIS Safety Console — Dark Editorial Design System */ /* ========================================================================= 1. Self-Hosted LAN Font Faces (No External CDNs) ========================================================================= */ @font-face` | display | `font-family: 'Unbounded';
  font-weight: 900;
  font-style: normal;
  font-displ...` |
| `@font-face` | display | `font-family: 'Inter';
  font-weight: 300 700;
  font-style: normal;
  font-displ...` |
| `/* ========================================================================= 2. Design Tokens (:root) Preserving ALL existing variable names & aliases; sharp rectangles; dark editorial palette ========================================================================= */ :root` | display, height | `/* Core Editorial Palette */
  --bg: #1c1918;
  --surface: #221e1d;
  --surface-...` |
| `html` | height | `background-color: #4a4947;
  color: var(--text);
  font-family: var(--font-sans)...` |
| `body` | display, height, min-height | `background-color: #4a4947;
  background-image: var(--grain);
  background-repeat...` |
| `/* Editorial 1200px Outer Frame with Hairline Borders */ .fx-frame` | display, position, height, min-height | `display: flex;
  flex-direction: column;
  flex: 1;
  width: 100%;
  max-width: ...` |
| `/* Tab Content JS display state rules (CRITICAL: preserve existing structure) */ .tab-content` | display | `display: none;` |
| `.tab-content.active` | display | `display: flex;` |
| `.tab-content.active.console-grid` | display | `display: grid;` |
| `/* ========================================================================= 4. Header & Navigation (Hairline Bar) ========================================================================= */ .app-header` | display, position, z-index, height | `height: 64px;
  background: var(--surface);
  border-bottom: 1px solid var(--bor...` |
| `.brand` | display | `display: flex;
  align-items: center;
  gap: 12px;` |
| `.brand-icon` | display, position, height | `width: 34px;
  height: 34px;
  background: var(--surface-2);
  border: 1px solid...` |
| `.pulse-ring` | opacity, position | `position: absolute;
  inset: -3px;
  border: 1px solid var(--accent);
  opacity:...` |
| `0%` | opacity, transform | `transform: scale(0.96); opacity: 0.6;` |
| `50%` | opacity | `opacity: 0.35;` |
| `100%` | opacity, transform | `transform: scale(0.96); opacity: 0.6;` |
| `.brand-text` | display | `display: flex;
  flex-direction: column;` |
| `.system-name` | display, transform, height | `font-family: var(--font-display);
  font-size: 15px;
  font-weight: 900;
  lette...` |
| `.system-sub` | transform | `font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  lett...` |
| `.status-indicator` | display | `display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  backgro...` |
| `.dot` | display, height | `width: 7px;
  height: 7px;
  background: var(--ok);
  display: inline-block;` |
| `0%, 100%` | opacity | `opacity: 1;` |
| `.status-label` | transform | `font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform:...` |
| `.policy-badge` | display | `display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  backgro...` |
| `.user-profile-badge` | display | `display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  backgro...` |
| `/* Role Badges (Admin / Operator) */ .role-badge` | transform | `font-size: 10px;
  font-weight: 800;
  padding: 2px 7px;
  text-transform: upper...` |
| `.btn-logout` | transform | `background: transparent;
  border: 1px solid var(--danger);
  color: var(--dange...` |
| `.btn-logout:hover` | transform | `background: rgba(255, 90, 90, 0.12);
  transform: translateY(-1px);` |
| `/* Tab Navigation Bar */ .tab-nav` | display, overflow | `display: flex;
  background: var(--surface);
  border-bottom: 1px solid var(--bo...` |
| `/* ========================================================================= 5. fx-title-band Component (First Child of Every Tab) Skewed Accent Slash behind one phrase; tilts 3deg more on hover ========================================================================= */ .fx-title-band` | display, overflow, position | `width: 100%;
  padding: 16px 20px;
  background: var(--surface);
  border: 1px s...` |
| `.fx-title-wrap` | position, z-index | `position: relative;
  z-index: 1;` |
| `.fx-slash-accent` | display, position | `position: relative;
  display: inline-block;
  color: var(--on-accent);
  margin...` |
| `.fx-slash-accent::before` | position, z-index, transform | `content: '';
  position: absolute;
  top: -2px;
  bottom: -2px;
  left: -22px;
 ...` |
| `.fx-title-band:hover .fx-slash-accent::before, .fx-slash-accent:hover::before` | transform | `transform: skewX(-24deg);` |
| `/* ========================================================================= 6. Tab 1 Hero: Editorial Grid + Wireframe Tunnel + Physics Tags ========================================================================= */ .fx-hero` | display, overflow, position | `grid-column: 1 / -1;
  display: grid;
  grid-template-columns: 1fr 372px;
  gap:...` |
| `.fx-hero-left` | display | `display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap...` |
| `.fx-hero-slash` | display, position, z-index | `position: relative;
  display: inline-block;
  color: var(--on-accent);
  paddin...` |
| `.fx-slash-line-1::before` | position, z-index, transform | `content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: -20px;
  right...` |
| `.fx-slash-line-2::before` | position, z-index, transform | `content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: -20px;
  right...` |
| `.fx-hero:hover .fx-slash-line-1::before, .fx-hero:hover .fx-slash-line-2::before` | transform | `transform: skewX(-24deg);` |
| `.fx-hero-sub` | height | `font-size: 13px;
  color: var(--text-muted);
  max-width: 580px;
  line-height: ...` |
| `.fx-hero-actions` | display | `display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 4px;` |
| `.fx-btn-open-alerts` | display, height, min-height | `display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
 ...` |
| `.fx-hero-hint` | display, transform | `font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color:...` |
| `/* Physics Draggable Tags Area */ .fx-tags-container` | display, position, height, min-height | `display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 60px;
  padding: 8px...` |
| `.fx-tag-pill` | display, transform | `display: inline-flex;
  align-items: center;
  justify-content: center;
  paddin...` |
| `.fx-tag-pill.fx-dragging` | z-index, !important | `cursor: grabbing;
  z-index: 1000 !important;
  box-shadow: 0 8px 24px rgba(0, 0...` |
| `.fx-tag-pill.fx-pinned` | z-index | `border-color: var(--accent);
  background: rgba(255, 106, 0, 0.18);
  color: var...` |
| `/* Hero Stats Strip (3 Cells) */ .fx-stats-strip` | display | `display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1px;
  background...` |
| `.fx-stat-cell` | display | `background: var(--surface-2);
  padding: 10px 14px;
  display: flex;
  flex-dire...` |
| `.fx-stat-label` | transform | `font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spaci...` |
| `.fx-stat-val` | display | `font-family: var(--font-display);
  font-size: 18px;
  font-weight: 900;
  color...` |
| `/* Right Tunnel Cell (372px) */ .fx-hero-tunnel-wrap` | display, overflow, position, height, min-height | `width: 372px;
  height: 100%;
  min-height: 280px;
  background: #141211;
  bord...` |
| `.fx-tunnel-header` | display | `padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  display: flex;
  ...` |
| `.fx-tunnel-canvas-box` | display, overflow, position | `flex: 1;
  position: relative;
  display: flex;
  align-items: center;
  justify...` |
| `#fx-tunnel-svg` | display, height | `width: 100%;
  height: 100%;
  display: block;` |
| `.btn-primary, .btn-demo, .btn-proc-start, .btn-detect-zone-action` | display, transform, height, min-height | `background: var(--accent);
  color: var(--on-accent);
  border: 1px solid var(--...` |
| `.btn-primary:hover:not(:disabled), .btn-demo:hover:not(:disabled), .btn-proc-start:hover:not(:disabled), .btn-detect-zone-action:hover:not(:disabled)` | transform | `background: var(--accent-hover);
  transform: translateY(-2px);
  box-shadow: 0 ...` |
| `.btn-primary:active:not(:disabled), .btn-demo:active:not(:disabled), .btn-proc-start:active:not(:disabled), .btn-detect-zone-action:active:not(:disabled)` | transform | `background: var(--accent-press);
  transform: translateY(1px);
  box-shadow: 0 1...` |
| `.btn-primary:disabled, .btn-proc-start:disabled, .btn-detect-zone-action:disabled` | opacity, transform | `opacity: 0.45;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;` |
| `/* Secondary Outlined Buttons */ .btn-secondary, .btn-proc-stop, .btn-icon, .btn-table-action, .btn-copy-logs` | display, transform, height, min-height | `background: transparent;
  color: var(--text);
  border: 1px solid var(--border)...` |
| `.btn-secondary:disabled, .btn-proc-stop:disabled` | opacity | `opacity: 0.35;
  cursor: not-allowed;` |
| `/* Danger Outlined Buttons */ .zone-delete-btn, .btn-revoke-key` | transform | `background: transparent;
  border: 1px solid var(--danger);
  color: var(--dange...` |
| `/* ========================================================================= 8. Form Inputs & Selects Hairline, Transparent, Accent Focus Ring, 44px Touch Targets, AA Contrast ========================================================================= */ .form-input, .filter-select, .filter-search-input` | height, min-height | `width: 100%;
  background: transparent;
  border: 1px solid var(--border);
  col...` |
| `.form-label` | display, transform | `display: block;
  font-size: 11px;
  font-weight: 700;
  text-transform: upperca...` |
| `/* Segmented Button Controls */ .seg-control` | display | `display: flex;
  border: 1px solid var(--border);
  background: var(--surface);` |
| `.seg-btn` | display, transform, height, min-height | `flex: 1;
  padding: 8px 10px;
  background: transparent;
  border: none;
  borde...` |
| `/* ========================================================================= 9. Panels, Cards, & Grid Cells (Hairline Grids, No Soft Shadows) ========================================================================= */ .console-grid` | display | `display: grid;
  grid-template-columns: 1fr 340px;
  gap: 16px;
  padding: 20px;` |
| `.panel` | position | `background: var(--surface);
  border: 1px solid var(--border);
  border-radius: ...` |
| `.panel-header` | display | `display: flex;
  align-items: center;
  justify-content: space-between;
  margin...` |
| `.panel-title-group` | display | `display: flex;
  align-items: center;
  gap: 10px;` |
| `.panel-title-group h2, .panel-header h3` | display, transform | `font-family: var(--font-display);
  font-size: 15px;
  font-weight: 900;
  text-...` |
| `.panel-desc` | height | `font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
  margin-bottom...` |
| `/* Secondary Filter Toolbar */ .alert-filter-bar` | display | `display: flex;
  gap: 10px;
  margin-bottom: 14px;
  padding: 10px;
  background...` |
| `.filter-item` | display | `display: flex;
  align-items: center;
  gap: 6px;` |
| `.filter-group` | display | `display: flex;
  border: 1px solid var(--border);` |
| `.filter-btn` | transform, height, min-height | `background: transparent;
  border: none;
  border-right: 1px solid var(--border)...` |
| `/* ========================================================================= 10. Alert Cards & Feed (2s Re-render Safe) ========================================================================= */ .feed-container` | display, overflow, height | `display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 720px;
  ove...` |
| `.alert-main-info` | display | `display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;` |
| `.alert-tags` | display | `display: flex;
  gap: 6px;
  flex-wrap: wrap;` |
| `/* Tilted Pill Tags */ .tag` | display, transform | `display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: 10...` |
| `.tag:nth-child(even)` | transform | `transform: rotate(1.5deg);` |
| `.alert-meta` | display | `display: flex;
  align-items: center;
  gap: 14px;
  font-size: 11px;
  color: v...` |
| `.meta-item` | display | `display: flex;
  align-items: center;
  gap: 6px;` |
| `.confidence-bar` | display, position, height | `display: inline-block;
  width: 50px;
  height: 4px;
  background: rgba(241, 230...` |
| `.confidence-fill` | display, height | `display: block;
  height: 100%;
  background: var(--accent);` |
| `/* Alert Action Feedback Buttons */ .alert-actions` | display | `display: flex;
  gap: 8px;
  align-items: center;` |
| `.btn-feedback` | display, transform, height, min-height | `display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  fo...` |
| `.btn-confirm:hover` | transform | `background: rgba(61, 220, 132, 0.15);
  transform: translateY(-1px);` |
| `.btn-false-alarm:hover` | transform | `background: rgba(255, 90, 90, 0.15);
  transform: translateY(-1px);` |
| `/* Status Badges with Mandatory Icon + Text (Never Color Alone) */ .feedback-status-badge` | display | `font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.06em;
  padding: 6px 12...` |
| `.info-tag` | transform | `font-size: 10px;
  font-weight: 800;
  padding: 2px 8px;
  border: 1px solid var...` |
| `.feed-empty-state h3, .feed-error-state h3` | display, transform | `font-family: var(--font-display);
  font-size: 14px;
  font-weight: 900;
  text-...` |
| `/* Threshold Lists */ .thresholds-list` | display | `display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;` |
| `.threshold-header` | display | `display: flex;
  justify-content: space-between;
  font-size: 12px;
  font-weigh...` |
| `.meter-bar` | height | `height: 4px;
  background: rgba(241, 230, 226, 0.12);
  width: 100%;` |
| `.meter-fill` | height | `height: 100%;
  background: var(--accent);` |
| `/* History List */ .history-list` | display | `display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 10px;` |
| `.history-item` | display | `display: flex;
  justify-content: space-between;
  align-items: center;
  paddin...` |
| `/* ========================================================================= 11. Tab 2: Live Stream Viewport & Controls ========================================================================= */ .stream-layout` | display | `display: flex;
  gap: 16px;
  padding: 20px;` |
| `.stream-viewport` | display, overflow, position, height, min-height | `width: 100%;
  min-height: 440px;
  background: #110f0f;
  border: 1px solid var...` |
| `.stream-img` | display, height | `width: 100%;
  height: auto;
  display: block;` |
| `.stream-badge` | transform | `font-size: 10px;
  font-weight: 800;
  padding: 2px 8px;
  border-radius: var(--...` |
| `.stream-live-indicator` | display, height | `width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--danger);
  ...` |
| `.stream-btn-row` | display | `display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 14px...` |
| `.stream-recent-events` | display | `display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;` |
| `.stream-event-chip` | transform | `padding: 4px 10px;
  font-size: 11px;
  background: var(--surface-2);
  border: ...` |
| `/* ========================================================================= 12. Tab 3: Draw Zone Canvas & Geometry Zone types differ by stroke pattern (solid/dashed/dotted) + text label ========================================================================= */ .zone-layout` | display | `display: flex;
  gap: 16px;
  padding: 20px;` |
| `.zone-controls-panel` | display | `width: 380px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;` |
| `.canvas-container` | display, overflow, position, height, min-height | `width: 100%;
  min-height: 480px;
  background: #110f0f;
  border: 1px solid var...` |
| `#zone-canvas` | display, height | `max-width: 100%;
  height: auto;
  display: block;` |
| `.zone-type-picker` | display | `display: flex;
  flex-direction: column;
  gap: 6px;` |
| `.zone-type-pill` | display, height, min-height | `display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  backgro...` |
| `.dot-color` | display, height | `width: 10px;
  height: 10px;
  display: inline-block;` |
| `.zone-mode-selector` | display | `display: grid;
  grid-template-columns: 1fr 1fr;
  border: 1px solid var(--borde...` |
| `.zone-draw-mode-btn` | display, transform, height, min-height | `background: transparent;
  border: none;
  border-right: 1px solid var(--border)...` |
| `.zone-draw-controls` | display | `display: flex;
  justify-content: space-between;
  align-items: center;
  paddin...` |
| `.zone-point-count` | display | `display: flex;
  align-items: center;
  gap: 6px;` |
| `.zones-list` | display, overflow, height | `display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
  max-h...` |
| `.zone-list-item` | display | `display: flex;
  align-items: center;
  justify-content: space-between;
  paddin...` |
| `.process-card` | display | `background: var(--surface-2);
  border: 1px solid var(--border);
  padding: 18px...` |
| `.proc-header` | display | `display: flex;
  justify-content: space-between;
  align-items: flex-start;
  ga...` |
| `.proc-title-wrap` | display | `display: flex;
  align-items: flex-start;
  gap: 10px;` |
| `.proc-name` | display, transform | `font-family: var(--font-display);
  font-size: 14px;
  font-weight: 900;
  text-...` |
| `.proc-dot` | display, height | `width: 8px;
  height: 8px;
  display: inline-block;
  margin-top: 4px;` |
| `/* Process Status Badges (Text + Icon) */ .proc-badge` | display, transform | `font-size: 10px;
  font-weight: 800;
  padding: 2px 7px;
  border-radius: var(--...` |
| `.proc-actions` | display | `display: flex;
  gap: 6px;` |
| `.proc-desc` | height | `font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;` |
| `.proc-meta` | display | `display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 10px;
  ...` |
| `.proc-logs-header` | display | `display: flex;
  justify-content: space-between;
  align-items: center;
  paddin...` |
| `.btn-toggle-logs` | display, transform | `background: transparent;
  border: none;
  color: var(--text-muted);
  font-size...` |
| `.chevron-icon` | transform | `transition: transform 0.2s ease;` |
| `.chevron-icon.rotated` | transform | `transform: rotate(180deg);` |
| `.proc-log-view` | overflow, height | `font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.45;
  color: ...` |
| `.data-table thead th` | position, z-index, transform | `background: var(--surface-2);
  color: var(--text-muted);
  font-size: 10px;
  f...` |
| `/* ========================================================================= 15. Modals & Dialogs (Grain Backdrop, Hairline Frame, Display Heading) ========================================================================= */ .modal-overlay` | position, z-index | `position: fixed;
  inset: 0;
  background: rgba(18, 16, 15, 0.88);
  background-...` |
| `.modal-card` | position | `width: 100%;
  background: var(--surface);
  border: 1px solid var(--border);
  ...` |
| `.modal-header` | display | `display: flex;
  align-items: center;
  justify-content: space-between;
  paddin...` |
| `.modal-header h3` | display, transform | `font-family: var(--font-display);
  font-size: 16px;
  font-weight: 900;
  text-...` |
| `.modal-desc` | height | `font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;` |
| `.modal-actions` | display | `display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;` |
| `/* Toast Notifications */ #toast-container` | display, position, z-index | `position: fixed;
  bottom: 24px;
  right: 24px;
  display: flex;
  flex-directio...` |
| `.toast` | display | `padding: 12px 18px;
  background: var(--surface);
  border: 1px solid var(--bord...` |
| `.fx-hero-tunnel-wrap` | height | `width: 100%;
    height: 280px;` |
| `.app-header` | height | `height: auto;
    padding: 14px 16px;
    flex-direction: column;
    align-item...` |
| `*, *::before, *::after` | !important | `animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !importa...` |
| `/* Additional Dynamic UI States & Utility Classes */ .proc-logs-body` | display, overflow, height | `display: none;
  max-height: 320px;
  overflow-y: auto;
  background: #0d0b0a;
 ...` |
| `.proc-logs-body.open` | display | `display: block;` |
| `.zone-list-info` | display | `display: flex;
  flex-direction: column;` |
| `.zone-list-actions` | display | `display: flex;
  align-items: center;
  gap: 6px;` |
| `.btn-zone-action-detect` | transform, height, min-height | `background: var(--accent);
  color: var(--on-accent);
  border: 1px solid var(--...` |
| `.btn-zone-action-load` | transform, height, min-height | `background: transparent;
  color: var(--text);
  border: 1px solid var(--border)...` |
| `.operator-badge` | display | `display: flex;
  align-items: center;
  gap: 6px;
  background-color: var(--surf...` |
| `.auth-lock-icon` | opacity | `font-size: 11px;
  opacity: 0.7;` |

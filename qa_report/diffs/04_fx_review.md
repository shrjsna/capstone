# fx.js In-Depth Audit Review

## 1. Document & Window Level Listeners

| Line | Target | Event | Code Snippet |
|---|---|---|---|
| 11 | `document` | `DOMContentLoaded` | `document.addEventListener('DOMContentLoaded', () => {` |
| 116 | `hero` | `pointermove` | `hero.addEventListener('pointermove', (e) => {` |
| 121 | `hero` | `pointerleave` | `hero.addEventListener('pointerleave', () => {` |
| 129 | `window` | `deviceorientation` | `window.addEventListener('deviceorientation', (e) => {` |
| 257 | `el` | `pointerdown` | `el.addEventListener('pointerdown', (e) => {` |
| 277 | `el` | `pointermove` | `el.addEventListener('pointermove', (e) => {` |
| 335 | `el` | `pointerup` | `el.addEventListener('pointerup', handlePointerEnd);` |
| 336 | `el` | `pointercancel` | `el.addEventListener('pointercancel', handlePointerEnd);` |
| 441 | `window` | `load` | `window.addEventListener('load', resetTagPositions);` |
| 442 | `window` | `resize` | `window.addEventListener('resize', resetTagPositions);` |
| 465 | `document` | `visibilitychange` | `document.addEventListener('visibilitychange', () => {` |

## 2. Event Propagation & Capture Modifiers

| Line | Method | Code Snippet |
|---|---|---|
| 35 | `preventDefault` | `e.preventDefault();` |
| 258 | `preventDefault` | `e.preventDefault();` |
| 259 | `setPointerCapture` | `el.setPointerCapture(e.pointerId);` |
| 301 | `releasePointerCapture` | `el.releasePointerCapture(e.pointerId);` |

## 3. DOM Insertions into document.body

None. `fx.js` does NOT append any elements to `document.body`.

## 4. Referenced DOM IDs in fx.js

| Line | ID Referenced | Belongs to Backup? | Purpose |
|---|---|---|---|
| 21 | `#fx-tunnel-container` | No (fx- added) | `const tunnelContainer = document.getElementById('fx-tunnel-c` |
| 22 | `#fx-tunnel-svg` | No (fx- added) | `const tunnelSvg = document.getElementById('fx-tunnel-svg');` |
| 23 | `#fx-tunnel-spokes` | No (fx- added) | `const spokesGroup = document.getElementById('fx-tunnel-spoke` |
| 24 | `#fx-tunnel-rects` | No (fx- added) | `const rectsGroup = document.getElementById('fx-tunnel-rects'` |
| 25 | `#fx-tunnel-dots` | No (fx- added) | `const dotsGroup = document.getElementById('fx-tunnel-dots');` |
| 26 | `#fx-tunnel-core` | No (fx- added) | `const coreCircle = document.getElementById('fx-tunnel-core')` |
| 27 | `#fx-btn-open-alerts` | No (fx- added) | `const openAlertsBtn = document.getElementById('fx-btn-open-a` |
| 29 | `#tab-alerts` | **YES (Shared)** | `const alertsTab = document.getElementById('tab-alerts');` |
| 227 | `#fx-tags-field` | No (fx- added) | `const tagsContainer = document.getElementById('fx-tags-field` |
| 476 | `#fx-stat-shown` | No (fx- added) | `const statShown = document.getElementById('fx-stat-shown');` |
| 477 | `#fx-stat-unreviewed` | No (fx- added) | `const statUnreviewed = document.getElementById('fx-stat-unre` |
| 478 | `#fx-stat-policy` | No (fx- added) | `const statPolicy = document.getElementById('fx-stat-policy')` |
| 480 | `#alert-count-badge` | **YES (Shared)** | `const alertCountBadge = document.getElementById('alert-count` |
| 481 | `#header-policy-ver` | **YES (Shared)** | `const headerPolicy = document.getElementById('header-policy-` |
| 482 | `#alert-feed-container` | **YES (Shared)** | `const feedContainer = document.getElementById('alert-feed-co` |

## 5. MutationObserver Loop Risk Analysis

- Line 4: `* Interactive Wireframe Tunnel + Draggable Physics Tags + MutationObserver Stats`
- Line 473: `// 2. Hero Stats Strip MutationObservers`
- Line 511: `const badgeObs = new MutationObserver(() => syncAlertsShown());`
- Line 512: `badgeObs.observe(alertCountBadge, { childList: true, characterData: true, subtree: true });`
- Line 517: `const policyObs = new MutationObserver(() => syncPolicyVer());`
- Line 518: `policyObs.observe(headerPolicy, { childList: true, characterData: true, subtree: true });`
- Line 523: `const feedObs = new MutationObserver(() => syncUnreviewed());`
- Line 524: `feedObs.observe(feedContainer, { childList: true, subtree: true });`

**Loop Analysis**: The 3 observers in `fx.js` observe `#alert-count-badge`, `#header-policy-ver`, and `#alert-feed-container`.
In their callbacks, they only mutate separate elements (`#fx-stat-shown`, `#fx-stat-policy`, `#fx-stat-unreviewed`).
They NEVER mutate their observed targets. Therefore, no infinite mutation loops can occur.

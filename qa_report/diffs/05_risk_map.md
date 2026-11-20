# Part 0: Change Risk Map

| Change Item | File : Line | Could it affect forms, inputs, buttons, modals or JS? | Evidence / Risk Level |
|---|---|---|---|
| `.fx-frame` wrapper around layout | `index.html`:35 | **YES (Layout / Stacking)** | Wraps `<main>` elements in flex column with max-width: 1200px. Changes grid alignment. Medium. |
| Removed Google Fonts links | `index.html`:7-9 | No (Typography only) | Self-hosted `@font-face` provides offline fallback. Low. |
| Added `fx.js` script tag with `defer` | `index.html`:993 | **YES (Execution / Listeners)** | Adds physics engine, touch-action: none on pills, pointer capture, and 3 MutationObservers. High. |
| Added `.fx-hero` spanning grid columns | `index.html`:44 | **YES (Layout / Scroll)** | Placed as first child of `#tab-alerts`. Has `overflow:hidden`. Medium. |
| Added `.fx-title-band` to all tabs | `index.html`: 여러 줄 | **YES (Grid / Flex child)** | Uses `grid-column: 1 / -1`. May affect layout in flex parents if flex-wrap missing. High. |
| Restyled `.tab-btn` min-height: 44px | `styles.css`:320 | No (A11y enhancement) | Increases touch target size. Low. |
| Changed `:root` color tokens | `styles.css`:20-45 | No (Cosmetic) | Preserved all original aliases. Low. |
| Sharp rectangles (`--radius: 0`) | `styles.css`:50 | No (Cosmetic) | Visual styling. Low. |
| `.tag` tilted pill rotations | `styles.css`:540 | No (Cosmetic) | Uses `transform: rotate(-1.5deg)`. Low. |
| Modal backdrop with grain | `styles.css`:820 | **YES (Modal Visibility)** | Uses backdrop-filter and grain background. Display flex controlled by JS. Medium. |
| `.sidebar-panel` inside `#tab-users` | `index.html`:825 | **SUSPICIOUS / HIGH** | In backup, `.sidebar-panel` was placed beside table. In 1024px media query, `.console-grid` stacks to single column, pushing Create Account form far below table. Also hidden if user not logged in as Admin. |

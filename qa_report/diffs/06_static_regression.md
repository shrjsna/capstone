# Part A: Static Regression Audit

## 1. ID Uniqueness and Completeness

- Total IDs in backup: 155 (Unique: 155)
- Total IDs in current: 168 (Unique: 168)
- Missing IDs: 0
- Duplicate IDs: 0

✓ **Zero missing IDs**: Every ID from the backup exists in current `index.html`.

✓ **Zero duplicate IDs**: Every ID in `index.html` is strictly unique.

## 2. Form Integrity and Button Containment

| Form ID | Found | Contained Input IDs | Has Submit Action |
|---|---|---|---|
| `#form-login` | Yes | login-error, login-username, login-password | Yes |
| `#form-create-user` | Yes | new-user-username, new-user-role, new-user-password | Yes |
| `#form-create-key` | Yes | new-key-label | Yes |
| `#form-change-pwd` | Yes | change-pwd-error, change-pwd-old, change-pwd-new, change-pwd-confirm | Yes |

## 3. Potential Click-Blocking or Overlay Issues

| Selector | Risk Flag | Declaration |
|---|---|---|
| `/* ========================================================================= 5. fx-title-band Component (First Child of Every Tab) Skewed Accent Slash behind one phrase; tilts 3deg more on hover ========================================================================= */ .fx-title-band` | overflow: hidden on container | `
  width: 100%;
  padding: 16px 20px;
  background: var(--su` |
| `/* ========================================================================= 6. Tab 1 Hero: Editorial Grid + Wireframe Tunnel + Physics Tags ========================================================================= */ .fx-hero` | overflow: hidden on container | `
  grid-column: 1 / -1;
  display: grid;
  grid-template-col` |
| `.fx-hero-slash` | High z-index layer | `
  position: relative;
  display: inline-block;
  color: var` |
| `.fx-tag-pill.fx-dragging` | High z-index layer | `
  cursor: grabbing;
  z-index: 1000 !important;
  box-shado` |
| `.fx-tag-pill.fx-pinned` | High z-index layer | `
  border-color: var(--accent);
  background: rgba(255, 106,` |
| `/* Right Tunnel Cell (372px) */ .fx-hero-tunnel-wrap` | overflow: hidden on container | `
  width: 372px;
  height: 100%;
  min-height: 280px;
  back` |
| `/* ========================================================================= 15. Modals & Dialogs (Grain Backdrop, Hairline Frame, Display Heading) ========================================================================= */ .modal-overlay` | High z-index layer | `
  position: fixed;
  inset: 0;
  background: rgba(18, 16, 1` |

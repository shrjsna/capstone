import re
from pathlib import Path
from collections import Counter

dashboard_dir = Path(r"c:\Games\repo-setup\repo-setup\dashboard")
backup_dir = Path(r"c:\Games\repo-setup\repo-setup\dashboard_backup_pre_restyle")
diffs_dir = Path(r"c:\Games\repo-setup\repo-setup\qa_report\diffs")

with open(dashboard_dir / "index.html", "r", encoding="utf-8") as f:
    curr_html = f.read()

with open(backup_dir / "index.html", "r", encoding="utf-8") as f:
    back_html = f.read()

with open(dashboard_dir / "styles.css", "r", encoding="utf-8") as f:
    curr_css = f.read()

with open(backup_dir / "styles.css", "r", encoding="utf-8") as f:
    back_css = f.read()

# 1. ID checks
curr_all_ids = re.findall(r'id=["\']([^"\'>]+)["\']', curr_html)
back_all_ids = re.findall(r'id=["\']([^"\'>]+)["\']', back_html)

curr_id_counts = Counter(curr_all_ids)
back_id_counts = Counter(back_all_ids)

duplicates = [k for k, v in curr_id_counts.items() if v > 1]
missing_ids = set(back_id_counts.keys()) - set(curr_id_counts.keys())
added_ids = set(curr_id_counts.keys()) - set(back_id_counts.keys())

# 2. Tag balancing & form containment
forms_to_check = ['form-login', 'form-create-user', 'form-create-key', 'form-change-pwd']
form_containment = {}

for fid in forms_to_check:
    m = re.search(rf'<form[^>]+id=["\']{fid}["\'][^>]*>(.*?)</form>', curr_html, re.DOTALL)
    if m:
        body = m.group(1)
        inputs = re.findall(r'id=["\']([^"\'>]+)["\']', body)
        buttons = re.findall(r'<button[^>]*>(.*?)</button>', body, re.DOTALL)
        types = re.findall(r'type=["\']([^"\'>]+)["\']', body)
        form_containment[fid] = {
            "found": True,
            "inputs": inputs,
            "has_submit": "submit" in types or any("type=\"submit\"" in b for b in buttons) or len(buttons) > 0,
            "button_count": len(buttons)
        }
    else:
        form_containment[fid] = {"found": False}

# 3. Blocking / Layer risks
# Check pointer-events, overflow:hidden, z-index, fixed layers
blocking_risks = []
css_blocks = re.findall(r'([^{}]+)\{([^{}]+)\}', curr_css)
for sel, body in css_blocks:
    sel_clean = ' '.join(sel.strip().split())
    if 'pointer-events: none' in body:
        blocking_risks.append((sel_clean, "pointer-events: none", body[:60]))
    if 'overflow: hidden' in body and any(x in sel_clean for x in ['hero', 'panel', 'frame', 'tab', 'title']):
        blocking_risks.append((sel_clean, "overflow: hidden on container", body[:60]))
    if '!important' in body and 'display' in body:
        blocking_risks.append((sel_clean, "!important on display override", body[:60]))
    if 'z-index' in body and any(x in sel_clean for x in ['grain', 'hero', 'tunnel', 'pill', 'overlay']):
        blocking_risks.append((sel_clean, "High z-index layer", body[:60]))

# Write 06_static_regression.md
with open(diffs_dir / "06_static_regression.md", "w", encoding="utf-8") as f:
    f.write("# Part A: Static Regression Audit\n\n")

    f.write("## 1. ID Uniqueness and Completeness\n\n")
    f.write(f"- Total IDs in backup: {len(back_all_ids)} (Unique: {len(back_id_counts)})\n")
    f.write(f"- Total IDs in current: {len(curr_all_ids)} (Unique: {len(curr_id_counts)})\n")
    f.write(f"- Missing IDs: {len(missing_ids)}\n")
    f.write(f"- Duplicate IDs: {len(duplicates)}\n\n")

    if missing_ids:
        f.write("### Missing IDs:\n")
        for m in sorted(missing_ids): f.write(f"- `#{m}`\n")
    else:
        f.write("✓ **Zero missing IDs**: Every ID from the backup exists in current `index.html`.\n\n")

    if duplicates:
        f.write("### Duplicate IDs:\n")
        for d in duplicates: f.write(f"- `#{d}` (Count: {curr_id_counts[d]})\n")
    else:
        f.write("✓ **Zero duplicate IDs**: Every ID in `index.html` is strictly unique.\n\n")

    f.write("## 2. Form Integrity and Button Containment\n\n")
    f.write("| Form ID | Found | Contained Input IDs | Has Submit Action |\n|---|---|---|---|\n")
    for fid, data in form_containment.items():
        if data["found"]:
            f.write(f"| `#{fid}` | Yes | {', '.join(data['inputs']) or 'None'} | {'Yes' if data['has_submit'] else 'NO'} |\n")
        else:
            f.write(f"| `#{fid}` | **NOT FOUND** | — | — |\n")

    f.write("\n## 3. Potential Click-Blocking or Overlay Issues\n\n")
    f.write("| Selector | Risk Flag | Declaration |\n|---|---|---|\n")
    for sel, flag, snippet in blocking_risks:
        f.write(f"| `{sel}` | {flag} | `{snippet}` |\n")

# Write 05_risk_map.md
with open(diffs_dir / "05_risk_map.md", "w", encoding="utf-8") as f:
    f.write("# Part 0: Change Risk Map\n\n")
    f.write("| Change Item | File : Line | Could it affect forms, inputs, buttons, modals or JS? | Evidence / Risk Level |\n")
    f.write("|---|---|---|---|\n")
    f.write("| `.fx-frame` wrapper around layout | `index.html`:35 | **YES (Layout / Stacking)** | Wraps `<main>` elements in flex column with max-width: 1200px. Changes grid alignment. Medium. |\n")
    f.write("| Removed Google Fonts links | `index.html`:7-9 | No (Typography only) | Self-hosted `@font-face` provides offline fallback. Low. |\n")
    f.write("| Added `fx.js` script tag with `defer` | `index.html`:993 | **YES (Execution / Listeners)** | Adds physics engine, touch-action: none on pills, pointer capture, and 3 MutationObservers. High. |\n")
    f.write("| Added `.fx-hero` spanning grid columns | `index.html`:44 | **YES (Layout / Scroll)** | Placed as first child of `#tab-alerts`. Has `overflow:hidden`. Medium. |\n")
    f.write("| Added `.fx-title-band` to all tabs | `index.html`: 여러 줄 | **YES (Grid / Flex child)** | Uses `grid-column: 1 / -1`. May affect layout in flex parents if flex-wrap missing. High. |\n")
    f.write("| Restyled `.tab-btn` min-height: 44px | `styles.css`:320 | No (A11y enhancement) | Increases touch target size. Low. |\n")
    f.write("| Changed `:root` color tokens | `styles.css`:20-45 | No (Cosmetic) | Preserved all original aliases. Low. |\n")
    f.write("| Sharp rectangles (`--radius: 0`) | `styles.css`:50 | No (Cosmetic) | Visual styling. Low. |\n")
    f.write("| `.tag` tilted pill rotations | `styles.css`:540 | No (Cosmetic) | Uses `transform: rotate(-1.5deg)`. Low. |\n")
    f.write("| Modal backdrop with grain | `styles.css`:820 | **YES (Modal Visibility)** | Uses backdrop-filter and grain background. Display flex controlled by JS. Medium. |\n")
    f.write("| `.sidebar-panel` inside `#tab-users` | `index.html`:825 | **SUSPICIOUS / HIGH** | In backup, `.sidebar-panel` was placed beside table. In 1024px media query, `.console-grid` stacks to single column, pushing Create Account form far below table. Also hidden if user not logged in as Admin. |\n")

print("Generated 05_risk_map.md and 06_static_regression.md")


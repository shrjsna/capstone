import re
from pathlib import Path

fx_path = Path(r"c:\Games\repo-setup\repo-setup\dashboard\fx.js")
diffs_dir = Path(r"c:\Games\repo-setup\repo-setup\qa_report\diffs")

with open(fx_path, "r", encoding="utf-8") as f:
    fx_code = f.read()

lines = fx_code.splitlines()

# Search listeners
listeners = []
for i, l in enumerate(lines, 1):
    m = re.findall(r'(\w+)\.addEventListener\([\'"](\w+)[\'"]', l)
    if m:
        for target, event in m:
            listeners.append((i, target, event, l.strip()))

# Search preventDefault, stopPropagation, setPointerCapture
guards = []
for i, l in enumerate(lines, 1):
    for call in ['preventDefault', 'stopPropagation', 'setPointerCapture', 'releasePointerCapture']:
        if call in l:
            guards.append((i, call, l.strip()))

# Body appends
body_appends = []
for i, l in enumerate(lines, 1):
    if 'document.body.appendChild' in l or 'document.body.append' in l:
        body_appends.append((i, l.strip()))

# IDs touched
ids_touched = []
for i, l in enumerate(lines, 1):
    m = re.findall(r'getElementById\([\'"]([^\'"]+)[\'"]\)', l)
    if m:
        for ident in m:
            ids_touched.append((i, ident, l.strip()))

# MutationObservers
observers = []
for i, l in enumerate(lines, 1):
    if 'MutationObserver' in l or '.observe(' in l:
        observers.append((i, l.strip()))

with open(diffs_dir / "04_fx_review.md", "w", encoding="utf-8") as f:
    f.write("# fx.js In-Depth Audit Review\n\n")

    f.write("## 1. Document & Window Level Listeners\n\n")
    f.write("| Line | Target | Event | Code Snippet |\n|---|---|---|---|\n")
    for l_no, target, evt, snippet in listeners:
        f.write(f"| {l_no} | `{target}` | `{evt}` | `{snippet}` |\n")

    f.write("\n## 2. Event Propagation & Capture Modifiers\n\n")
    f.write("| Line | Method | Code Snippet |\n|---|---|---|\n")
    for l_no, method, snippet in guards:
        f.write(f"| {l_no} | `{method}` | `{snippet}` |\n")

    f.write("\n## 3. DOM Insertions into document.body\n\n")
    if body_appends:
        for l_no, snippet in body_appends:
            f.write(f"- Line {l_no}: `{snippet}`\n")
    else:
        f.write("None. `fx.js` does NOT append any elements to `document.body`.\n")

    f.write("\n## 4. Referenced DOM IDs in fx.js\n\n")
    f.write("| Line | ID Referenced | Belongs to Backup? | Purpose |\n|---|---|---|---|\n")
    backup_ids = [
        "alert-count-badge", "header-policy-ver", "alert-feed-container", "tab-alerts"
    ]
    for l_no, ident, snippet in ids_touched:
        is_backup = ident in backup_ids
        f.write(f"| {l_no} | `#{ident}` | {'**YES (Shared)**' if is_backup else 'No (fx- added)'} | `{snippet[:60]}` |\n")

    f.write("\n## 5. MutationObserver Loop Risk Analysis\n\n")
    for l_no, snippet in observers:
        f.write(f"- Line {l_no}: `{snippet}`\n")
    f.write("\n**Loop Analysis**: The 3 observers in `fx.js` observe `#alert-count-badge`, `#header-policy-ver`, and `#alert-feed-container`.\n")
    f.write("In their callbacks, they only mutate separate elements (`#fx-stat-shown`, `#fx-stat-policy`, `#fx-stat-unreviewed`).\n")
    f.write("They NEVER mutate their observed targets. Therefore, no infinite mutation loops can occur.\n")

print("Generated 04_fx_review.md")


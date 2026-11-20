import re
from pathlib import Path

dashboard_dir = Path(r"c:\Games\repo-setup\repo-setup\dashboard")
backup_dir = Path(r"c:\Games\repo-setup\repo-setup\dashboard_backup_pre_restyle")
diffs_dir = Path(r"c:\Games\repo-setup\repo-setup\qa_report\diffs")

with open(dashboard_dir / "styles.css", "r", encoding="utf-8") as f:
    curr_css = f.read()

with open(backup_dir / "styles.css", "r", encoding="utf-8") as f:
    back_css = f.read()

def parse_blocks(css):
    blocks = {}
    pattern = re.compile(r'([^{}]+)\{([^{}]+)\}')
    for match in pattern.finditer(css):
        sel = ' '.join(match.group(1).strip().split())
        body = match.group(2).strip()
        blocks[sel] = body
    return blocks

curr_blocks = parse_blocks(curr_css)
back_blocks = parse_blocks(back_css)

added_selectors = set(curr_blocks.keys()) - set(back_blocks.keys())
removed_selectors = set(back_blocks.keys()) - set(curr_blocks.keys())
shared_selectors = set(curr_blocks.keys()) & set(back_blocks.keys())

# Analyze root variables
def parse_root_vars(css):
    m = re.search(r':root\s*\{([^}]+)\}', css)
    if not m: return {}
    vars_dict = {}
    for line in m.group(1).split(';'):
        line = line.strip()
        if line.startswith('--'):
            parts = line.split(':', 1)
            if len(parts) == 2:
                vars_dict[parts[0].strip()] = parts[1].strip()
    return vars_dict

curr_vars = parse_root_vars(curr_css)
back_vars = parse_root_vars(back_css)

# Find critical property rules in current css
crit_props = ['display', 'visibility', 'opacity', 'pointer-events', 'overflow', 'position', 'z-index', 'transform', 'height', 'min-height', '!important']
crit_rules = []
for sel, body in curr_blocks.items():
    hits = [p for p in crit_props if p in body]
    if hits:
        crit_rules.append((sel, hits, body))

# Global selectors
global_sels = ['*', 'body', 'button', 'input', 'select', 'textarea', 'form', 'label', 'a', 'dialog', 'table', 'html']
global_rules = [(sel, body) for sel, body in curr_blocks.items() if any(g == sel or sel.startswith(g + ' ') or sel.startswith(g + ':') or (', ' + g) in sel for g in global_sels)]

# Media queries
curr_media = re.findall(r'@media[^{]+\{', curr_css)
back_media = re.findall(r'@media[^{]+\{', back_css)

with open(diffs_dir / "03_styles_diff.md", "w", encoding="utf-8") as f:
    f.write("# styles.css Detailed Diff Report\n\n")
    
    f.write("## 1. :root Tokens Comparison\n\n")
    f.write("| Variable | Current Value | Backup Value | Status |\n|---|---|---|---|\n")
    all_vars = sorted(set(curr_vars.keys()) | set(back_vars.keys()))
    for v in all_vars:
        c_val = curr_vars.get(v, "—")
        b_val = back_vars.get(v, "—")
        if c_val == b_val:
            status = "Unchanged"
        elif b_val == "—":
            status = "**ADDED**"
        elif c_val == "—":
            status = "**REMOVED**"
        else:
            status = "**CHANGED**"
        # Truncate data URI if too long
        c_disp = c_val[:45] + "..." if len(c_val) > 50 else c_val
        b_disp = b_val[:45] + "..." if len(b_val) > 50 else b_val
        f.write(f"| `{v}` | `{c_disp}` | `{b_disp}` | {status} |\n")
        
    f.write(f"\n## 2. Added Selectors ({len(added_selectors)})\n\n")
    for s in sorted(added_selectors)[:60]:
        f.write(f"- `{s}`\n")
    if len(added_selectors) > 60:
        f.write(f"- *... and {len(added_selectors) - 60} more*\n")

    f.write(f"\n## 3. Removed Selectors ({len(removed_selectors)})\n\n")
    for s in sorted(removed_selectors)[:60]:
        f.write(f"- `{s}`\n")
    if len(removed_selectors) > 60:
        f.write(f"- *... and {len(removed_selectors) - 60} more*\n")

    f.write(f"\n## 4. Media Queries Comparison\n\n")
    f.write("### Backup Media Queries:\n")
    for m in back_media: f.write(f"- `{m.strip()}`\n")
    f.write("\n### Current Media Queries:\n")
    for m in curr_media: f.write(f"- `{m.strip()}`\n")

    f.write(f"\n## 5. Critical Property Rules (display, overflow, pointer-events, z-index, !important)\n\n")
    f.write("| Selector | Critical Properties Found | Declarations |\n|---|---|---|\n")
    for sel, hits, body in crit_rules:
        f.write(f"| `{sel}` | {', '.join(hits)} | `{body[:80] + ('...' if len(body)>80 else '')}` |\n")

print("Generated 03_styles_diff.md")


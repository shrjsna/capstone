import difflib
import re
from pathlib import Path
from html.parser import HTMLParser

dashboard_dir = Path(r"c:\Games\repo-setup\repo-setup\dashboard")
backup_dir = Path(r"c:\Games\repo-setup\repo-setup\dashboard_backup_pre_restyle")
diffs_dir = Path(r"c:\Games\repo-setup\repo-setup\qa_report\diffs")

# =========================================================================
# 2. Detailed index.html Diff
# =========================================================================
with open(dashboard_dir / "index.html", "r", encoding="utf-8") as f:
    curr_html = f.read().replace('\r\n', '\n')

with open(backup_dir / "index.html", "r", encoding="utf-8") as f:
    back_html = f.read().replace('\r\n', '\n')

html_diff = list(difflib.unified_diff(
    back_html.splitlines(keepends=True),
    curr_html.splitlines(keepends=True),
    fromfile="backup/index.html",
    tofile="current/index.html",
    n=3
))

# Parse DOM structure using HTMLParser to find added, removed, reparented elements
class DomParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.elements = []
        self.ids = {}
        self.classes = set()
    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        parent = self.stack[-1] if self.stack else None
        elem_info = {
            "tag": tag,
            "attrs": attr_dict,
            "parent": parent["attrs"].get("id") or parent["attrs"].get("class") or parent["tag"] if parent else "ROOT"
        }
        if "id" in attr_dict:
            self.ids[attr_dict["id"]] = elem_info
        if "class" in attr_dict:
            for c in attr_dict["class"].split():
                self.classes.add(c)
        self.stack.append(elem_info)
        self.elements.append(elem_info)
    def handle_endtag(self, tag):
        if self.stack:
            self.stack.pop()

p_curr = DomParser()
p_curr.feed(curr_html)

p_back = DomParser()
p_back.feed(back_html)

# Check IDs whose parent changed
reparented_ids = []
for id_name, b_info in p_back.ids.items():
    if id_name in p_curr.ids:
        c_info = p_curr.ids[id_name]
        if b_info["parent"] != c_info["parent"]:
            reparented_ids.append((id_name, b_info["parent"], c_info["parent"]))

# Write index diff report
with open(diffs_dir / "02_index_diff.md", "w", encoding="utf-8") as f:
    f.write("# index.html Structural Diff Report\n\n")
    f.write("## 1. Summary of Changes\n")
    f.write("- **Fonts / External Links REMOVED**: Removed 3 Google Fonts `<link>` tags (lines 7-9 in backup).\n")
    f.write("- **Outer Layout Wrapper ADDED**: Added `<div class=\"fx-frame\">` wrapping `<header>`, `<nav>`, and all 6 `<main>` tab containers.\n")
    f.write("- **Script Tag ADDED**: Added `<script src=\"fx.js\" defer></script>` after `app.js`.\n")
    f.write("- **Tab 1 Hero ADDED**: Added `<section class=\"fx-hero\">` at the start of `#tab-alerts` containing `.fx-hero-left`, `#fx-btn-open-alerts`, `.fx-tags-container` (9 draggable pills), `.fx-stats-strip` (3 stat cells), and `#fx-tunnel-zone` (SVG wireframe tunnel).\n")
    f.write("- **Tab Title Bands ADDED**: Added `<div class=\"fx-title-band\">` with skewed accent slash as first child to tabs: `#tab-stream`, `#tab-zones`, `#tab-control`, `#tab-users`, `#tab-audit`.\n\n")
    f.write("## 2. Reparented Elements (Parent Changes)\n")
    f.write(f"Total reparented IDs: {len(reparented_ids)}\n\n")
    f.write("| Element ID | Backup Parent | Current Parent |\n|---|---|---|\n")
    for id_name, b_parent, c_parent in reparented_ids:
        f.write(f"| `#{id_name}` | `{b_parent}` | `{c_parent}` |\n")
    f.write("\n## 3. Raw Unified Diff (First 150 lines)\n```diff\n")
    f.write("".join(html_diff[:150]))
    f.write("\n```\n")

print("Generated 02_index_diff.md")


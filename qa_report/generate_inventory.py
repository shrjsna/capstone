import os
import hashlib
import difflib
import re
from pathlib import Path

dashboard_dir = Path(r"c:\Games\repo-setup\repo-setup\dashboard")
backup_dir = Path(r"c:\Games\repo-setup\repo-setup\dashboard_backup_pre_restyle")
diffs_dir = Path(r"c:\Games\repo-setup\repo-setup\qa_report\diffs")

def get_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().upper()

# 1. Files Comparison
dash_files = {p.name: p for p in dashboard_dir.iterdir() if p.is_file()}
backup_files = {p.name: p for p in backup_dir.iterdir() if p.is_file()}

all_names = sorted(set(dash_files.keys()) | set(backup_files.keys()))

files_summary = []
files_summary.append("# File Comparison Inventory\n")
files_summary.append("| File Name | Status | Current Size | Current SHA256 | Backup Size | Backup SHA256 |")
files_summary.append("|---|---|---|---|---|---|")

for name in all_names:
    curr_p = dash_files.get(name)
    back_p = backup_files.get(name)
    
    if curr_p and not back_p:
        status = "ADDED"
        c_size = curr_p.stat().st_size
        c_hash = get_hash(curr_p)
        files_summary.append(f"| `{name}` | **ADDED** | {c_size} B | `{c_hash}` | — | — |")
    elif back_p and not curr_p:
        status = "REMOVED"
        b_size = back_p.stat().st_size
        b_hash = get_hash(back_p)
        files_summary.append(f"| `{name}` | **REMOVED** | — | — | {b_size} B | `{b_hash}` |")
    else:
        c_size = curr_p.stat().st_size
        c_hash = get_hash(curr_p)
        b_size = back_p.stat().st_size
        b_hash = get_hash(back_p)
        if c_hash == b_hash:
            status = "IDENTICAL"
            files_summary.append(f"| `{name}` | IDENTICAL | {c_size} B | `{c_hash}` | {b_size} B | `{b_hash}` |")
        else:
            status = "MODIFIED"
            files_summary.append(f"| `{name}` | **MODIFIED** | {c_size} B | `{c_hash}` | {b_size} B | `{b_hash}` |")

with open(diffs_dir / "01_files_summary.md", "w", encoding="utf-8") as f:
    f.write("\n".join(files_summary) + "\n")

print("Generated 01_files_summary.md")


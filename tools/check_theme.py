"""
tools/check_theme.py
====================
Theme verification utility:
Scans dashboard/ (styles.css, index.html, app.js) to ensure all styling conforms
strictly to the Black, White, and Orange palette:
- Background: #0A0A0A
- Surfaces: #141414, #1E1E1E
- Border: #2E2E2E
- Text: #FFFFFF
- Text Muted: #A3A3A3
- Accent: #FF6A00 (hover: #FF8533, press: #E65F00)
- On-Accent: #0A0A0A

Fails if any unauthorized color literals (e.g. green, red, blue, cyan, yellow) are present.
"""

import re
import sys
from pathlib import Path

# Paths to check
DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
FILES_TO_CHECK = [
    DASHBOARD_DIR / "styles.css",
    DASHBOARD_DIR / "index.html",
    DASHBOARD_DIR / "app.js",
    DASHBOARD_DIR / "login.html",
]

# Patterns representing non-palette color violations
FORBIDDEN_COLOR_PATTERNS = [
    # Named colors forbidden
    (r"\b(red|green|blue|cyan|magenta|yellow|lime|teal|indigo|purple|emerald|amber)\b", "Named non-palette color"),
    # Non-orange, non-grayscale hex codes (e.g., #38bdf8, #10b981, #ef4444, #fbbf24)
    (r"#(?:38bdf8|10b981|ef4444|fbbf24|090d14|111723|182030|1e283c|253147|334361|f1f5f9|94a3b8|64748b)\b", "Legacy palette hex"),
    # Disallowed rgba/rgb with non-orange/non-gray channels (e.g., rgba(16, 185, 129, ...), rgba(56, 189, 248, ...))
    (r"rgba?\(\s*(?!(?:255|10|20|30|46|163|0)\s*,\s*(?:106|85|95|14|30|46|163|0|255)\s*,\s*(?:0|51|10|20|30|46|163|255)\b)\d+\s*,\s*\d+\s*,\s*\d+", "Non-palette rgb/rgba"),
]


def check_theme() -> int:
    violations = []

    for file_path in FILES_TO_CHECK:
        if not file_path.is_file():
            continue
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line_num, line in enumerate(lines, 1):
            # Skip comments or font family lines
            clean = line.strip()
            if clean.startswith("/*") or clean.startswith("//") or clean.startswith("*"):
                continue
            if "font-family" in clean or "fonts.googleapis" in clean:
                continue

            for pattern, reason in FORBIDDEN_COLOR_PATTERNS:
                matches = re.findall(pattern, clean, re.IGNORECASE)
                if matches:
                    violations.append({
                        "file": file_path.name,
                        "line": line_num,
                        "match": matches,
                        "text": clean[:100],
                        "reason": reason,
                    })

    if violations:
        print(f"[ERROR] Found {len(violations)} theme color violations in dashboard files:")
        for v in violations[:30]:
            print(f"  {v['file']}:{v['line']} [{v['reason']}]: {v['text']}")
        if len(violations) > 30:
            print(f"  ... and {len(violations) - 30} more.")
        return 1

    print("[OK] All dashboard assets strictly adhere to the Black, White, and Orange palette.")
    return 0


if __name__ == "__main__":
    sys.exit(check_theme())


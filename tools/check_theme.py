"""
tools/check_theme.py
====================
Theme verification utility:
Scans dashboard/ (styles.css, index.html, app.js, login.html) to ensure all styling conforms
strictly to the AEGIS Dark Editorial / Black, White, and Orange palette tokens.
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

ALLOWED_RGB_PREFIXES = [
    r"241\s*,\s*230\s*,\s*226",  # --text / --border #f1e6e2
    r"255\s*,\s*90\s*,\s*90",    # --danger #ff5a5a
    r"61\s*,\s*220\s*,\s*132",   # --ok #3ddc84
    r"255\s*,\s*106\s*,\s*0",    # --accent #ff6a00
    r"255\s*,\s*133\s*,\s*51",   # --accent-hover #ff8533
    r"230\s*,\s*95\s*,\s*0",     # --accent-press #e65f00
    r"255\s*,\s*152\s*,\s*0",    # --warning #ff9800
    r"18\s*,\s*16\s*,\s*15",     # --bg backdrop
    r"28\s*,\s*25\s*,\s*24",     # --bg #1c1918
    r"34\s*,\s*30\s*,\s*29",     # --surface #221e1d
    r"43\s*,\s*38\s*,\s*37",     # --surface-2 #2b2625
    r"10\s*,\s*10\s*,\s*10",     # black
    r"20\s*,\s*20\s*,\s*20",     # dark gray
    r"30\s*,\s*30\s*,\s*30",     # dark gray
    r"46\s*,\s*46\s*,\s*46",     # border gray
    r"163\s*,\s*163\s*,\s*163",  # text muted gray
    r"255\s*,\s*255\s*,\s*255",  # white
    r"0\s*,\s*0\s*,\s*0",        # pure black
]

_allowed_rgb_regex = "|".join(ALLOWED_RGB_PREFIXES)

# Patterns representing non-palette color violations
FORBIDDEN_COLOR_PATTERNS = [
    # Named colors forbidden
    (r"\b(red|green|blue|cyan|magenta|yellow|lime|teal|indigo|purple|emerald|amber)\b", "Named non-palette color"),
    # Non-orange, non-grayscale legacy hex codes
    (r"#(?:38bdf8|10b981|ef4444|fbbf24|090d14|111723|182030|1e283c|253147|334361|f1f5f9|94a3b8|64748b)\b", "Legacy palette hex"),
    # Disallowed rgba/rgb with non-palette channels
    (rf"rgba?\(\s*(?!(?:{_allowed_rgb_regex})\b)\d+\s*,\s*\d+\s*,\s*\d+", "Non-palette rgb/rgba"),
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

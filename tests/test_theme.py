"""
tests/test_theme.py
===================
Automated verification that dashboard frontend code (HTML, CSS, JS)
strictly adheres to the AEGIS Black, White, and Orange design palette.
"""

from tools.check_theme import check_theme


def test_theme_compliance():
    """All dashboard styling files must adhere to the Black, White, and Orange palette."""
    assert check_theme() == 0, "Theme check failed! Non-palette colors detected."


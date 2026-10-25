"""WCAG contrast checks for the app's own palette (`Braaanding`).

The twelve collection palettes are HDS token names, and `paletteContrast.test.js`
proves each of them against the HDS colour table. The app's palette is a row of
hexadecimal colours an operator edits in the admin, so no test can see its
values: the check goes where they are changed instead (`Braaanding.clean`), and
it asks for exactly what that test asks of the twelve.

Pure functions, no Django: the formula is WCAG 2.1's relative luminance.
"""

import re

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

WHITE = "#FFFFFF"
# `brick-dark` in the HDS colour table: the front door's alpha warning
# (`.login-alpha`, 16px bold, so normal text) is painted in it on `color_02`.
LOGIN_ALPHA = "#800E04"

AA_NORMAL = 4.5


def _channel(hex_color, index):
    value = int(hex_color[1 + index * 2 : 3 + index * 2], 16) / 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color):
    return (
        0.2126 * _channel(hex_color, 0)
        + 0.7152 * _channel(hex_color, 1)
        + (0.0722 * _channel(hex_color, 2))
    )


def contrast_ratio(first, second):
    a, b = relative_luminance(first), relative_luminance(second)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# (label, foreground role or fixed hex, background role or fixed hex). The same
# pairings `paletteContrast.test.js` judges for every palette: body text on the
# page, the primary button's label on its fill, the hero's text on the hero, the
# text colour of the secondary button and of the content links on white, and the
# front door's warning on the page. `color_04` is also what a content link falls
# back to when `color_01` does not read on both white and `color_02`.
#
# The keyboard ring is not here: it is two bands, black and white, and one of the
# two reaches 3:1 on any surface at all, so no palette can fail it.
PAIRINGS = (
    ("body text (color_04 on color_02)", "color_04", "color_02"),
    ("primary button (color_06 on color_01)", "color_06", "color_01"),
    ("hero text (color_05 on color_03)", "color_05", "color_03"),
    ("secondary button and links (color_04 on white)", "color_04", WHITE),
    ("front door warning (brick-dark on color_02)", LOGIN_ALPHA, "color_02"),
)


def contrast_failures(colors):
    """The pairings of `colors` (a `color_01`..`color_06` map of hex) under 4.5:1.

    Returns human-readable lines, empty when the palette is fit to paint with.
    """
    failures = []
    for label, foreground, background in PAIRINGS:
        fg = colors.get(foreground, foreground)
        bg = colors.get(background, background)
        ratio = contrast_ratio(fg, bg)
        if ratio < AA_NORMAL:
            failures.append(f"{label}: {ratio:.2f}:1, needs {AA_NORMAL}:1")
    return failures

"""The app's own palette, written into the HTML the server hands out.

The pages that are not a collection's are painted with the six CSS variables
`--color-braaanding-01` … `--color-braaanding-06`, and the Koros wave type is read
by script. Both come from the `Braaanding` row an operator edits in the admin
(`core.models.braaanding`), so `spa_index` writes them into `index.html` as it
serves it. There is no request for them and no flash of the wrong colours: they
are in the first byte.

* The colours go in a `<style>` block in the `<head>`, which the CSP already
  allows (`style-src 'unsafe-inline'`). The selector is `html:root`, one type
  selector more specific than the `:root` of the fallback in
  `frontend/src/styles/oiueei-theme.css`, so the served values win whatever the
  order of the two in the document.
* The koro goes in `<meta name="braaanding-koro">`: a script reads a meta
  synchronously, and the CSP has no `'unsafe-inline'` for scripts, so an inline
  block of data is not an option and an extra request would be a flash.

Every value is checked again here, although the model validated it on save: this
writes into markup, and a value that is not exactly `#RRGGBB` (or a koro that is not
one of the six) is replaced by its seeded default rather than escaped and trusted.
"""

from core.models.braaanding import DEFAULT_COLORS, DEFAULT_KORO, braaanding
from core.models.theeeme import KORO_CHOICES
from core.services.palette_contrast import HEX_RE

KORO_META = "braaanding-koro"
_KOROS = {value for value, _label in KORO_CHOICES}


def palette_style_and_meta(palette):
    """The `<style>` and `<meta>` tags for ``palette`` (the dict `braaanding()` gives)."""
    declarations = []
    for index, role in enumerate(DEFAULT_COLORS, start=1):
        value = palette.get(role)
        if not isinstance(value, str) or not HEX_RE.match(value):
            value = DEFAULT_COLORS[role]
        declarations.append(f"--color-braaanding-{index:02d}:{value}")
    koro = palette.get("koro")
    if koro not in _KOROS:
        koro = DEFAULT_KORO
    return (
        f'<style id="braaanding">html:root{{{";".join(declarations)}}}</style>'
        f'<meta name="{KORO_META}" content="{koro}">'
    )


def inject_app_palette(html):
    """``html`` with the app's palette written into its ``<head>``.

    An ``index.html`` without ``</head>`` comes back as it was.
    """
    if "</head>" not in html:
        return html
    return html.replace("</head>", palette_style_and_meta(braaanding()) + "</head>", 1)

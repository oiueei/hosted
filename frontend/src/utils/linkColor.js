import TOKEN_HEX from './colorTokens';

// Which colour a text link in the page's content takes, and the arithmetic behind
// the choice. The WCAG 2.1 formula is the one `test/paletteContrast.test.js`
// holds the twelve palettes to.

const AA_NORMAL = 4.5;

function relativeLuminance(hex) {
  const h = hex.replace('#', '');
  const chan = (i) => {
    const c = parseInt(h.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * chan(0) + 0.7152 * chan(2) + 0.0722 * chan(4);
}

/** WCAG contrast ratio between two `#rrggbb` colours. */
export function contrastRatio(a, b) {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/**
 * The hex behind a colour token: an HDS token from the table, or one of the app's
 * own (`braaanding-0N`), whose value the server wrote into the page as
 * `--color-braaanding-0N` — read from the root at the moment it is needed, since an
 * operator can change it in the admin. `null` when it cannot be known.
 */
export function tokenHex(token) {
  if (!token) return null;
  if (TOKEN_HEX[token]) return TOKEN_HEX[token];
  if (token.startsWith('braaanding-') && typeof document !== 'undefined') {
    const value = getComputedStyle(document.documentElement)
      .getPropertyValue(`--color-${token}`)
      .trim();
    return /^#[0-9a-f]{6}$/i.test(value) ? value : null;
  }
  return null;
}

/**
 * The token a content link takes in a theeeme: `color_01` (the primary button's
 * fill) when it reaches 4.5:1 on both surfaces links sit on — white (tables,
 * cards) and the page background `color_02` — else `color_04`, the theeeme's text.
 * `null` for a theeeme without those colours (the stylesheet's default stands).
 */
export function linkColorToken(tc) {
  if (!tc?.color_01 || !tc.color_02) return tc?.color_04 || null;
  const link = tokenHex(tc.color_01);
  const page = tokenHex(tc.color_02);
  const readable =
    link &&
    page &&
    contrastRatio(link, TOKEN_HEX.white) >= AA_NORMAL &&
    contrastRatio(link, page) >= AA_NORMAL;
  return readable ? tc.color_01 : tc.color_04 || null;
}

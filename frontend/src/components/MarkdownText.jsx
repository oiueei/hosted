import { useNavigate, useInRouterContext } from 'react-router';

/**
 * Renders a subset of Markdown as sanitised HTML.
 *
 * Supported syntax:
 *   **bold**           -> <strong>
 *   *italic* / _italic_ -> <em>
 *   - bullet (also `* ` and `+ `) -> <ul><li>
 *   1. numbered        -> <ol><li>
 *   [text](url)        -> <a> — http(s) (balanced parentheses allowed), `www.…`
 *     (read as https), `mailto:` and site paths (`/collections/…`); anything else
 *     (`javascript:`, `data:`…) is not a link and shows its label as text.
 *     A bare `https://…` or `www.…` in the text is linked too.
 *     A link to this site (a path or an absolute URL that, resolved against this
 *     origin, stays on it — `/\evil.com` does not, and is no link) opens in
 *     the same tab through the router; any other http(s) link in a new one.
 *   | a | b | pipe tables (GFM: header row + |---|---| separator) -> <table>
 *   # / ## / ###+ heading -> <h3> / <h4> / <h5> (deeper levels cap at <h5> —
 *     the page around this component already owns h1/h2, so a bio can't
 *     outrank the page's own outline)
 *
 * `variant="card"` (the description on a thing's card): titles come out as one
 * line of ordinary text — no <hN>, no `#` — and `**x**` as x, without <strong>;
 * italics and links stay. Anywhere else nothing changes.
 *
 * All other content is HTML-escaped before processing.
 */

function escapeHtml(str) {
  return (
    str
      // NUL is dropped, not escaped: renderInline parks extracted links behind
      // NUL-delimited placeholders, so user text must not be able to forge one.
      .replace(/\0/g, '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
  );
}

function sanitizeUrl(url) {
  try {
    const parsed = new URL(url, window.location.origin);
    return ['http:', 'https:'].includes(parsed.protocol) ? url : '#';
  } catch {
    return '#';
  }
}

// What a link target means: a site path or an absolute URL of this origin is
// **internal** (same tab, navigated by the router); any other http(s) address is
// **external** (new tab); `mailto:` stays in the same tab; everything else
// (`javascript:`, `data:`, a relative `foo`…) is no link at all. `url` arrives
// HTML-escaped, and what comes back is still escaped — it goes into an href.
// `sanitizeUrl`, exported below, keeps its own contract.
function resolveLink(raw) {
  const url = raw.trim();
  // A path is internal only if, resolved against this origin, it stays here: the
  // browser reads `\` as `/` and drops tabs, so `/\evil.com` and `/<tab>/evil.com`
  // both land on another site. One that leaves is no link at all.
  if (url.startsWith('/')) {
    try {
      const parsed = new URL(url, window.location.origin);
      if (parsed.origin !== window.location.origin) return null;
      return { href: `${parsed.pathname}${parsed.search}${parsed.hash}`, kind: 'internal' };
    } catch {
      return null;
    }
  }
  if (/^mailto:[^\s]+$/i.test(url)) return { href: url, kind: 'mailto' };
  const candidate = /^www\./i.test(url) ? `https://${url}` : url;
  if (!/^https?:\/\//i.test(candidate)) return null;
  try {
    const parsed = new URL(candidate);
    if (!parsed.hostname) return null;
    if (parsed.origin === window.location.origin) {
      return { href: `${parsed.pathname}${parsed.search}${parsed.hash}`, kind: 'internal' };
    }
    return { href: candidate, kind: 'external' };
  } catch {
    return null;
  }
}

function anchor({ href, kind }, label) {
  if (kind === 'internal') return `<a href="${href}" data-internal>${label}</a>`;
  if (kind === 'mailto') return `<a href="${href}">${label}</a>`;
  return `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`;
}

// Bold and italics. An italic mark must be glued to the word on its inside:
// `*like this*` is emphasis, `2 * 3 * 4` is arithmetic. On a card (`plain`) bold is only its text: the description
// there is a few quiet lines and must not shout over the card's own title.
//
// No lookbehind anywhere in this file: Safari before 16.4 cannot parse a regular
// expression literal that has one, so it fails to load this whole module, not
// just the italics (test/markdownNoLookbehind.test.js keeps it out). The mark's
// outer edge is captured instead (`(^|\W)`) and given back. The lazy `??` keeps
// `*a* y *b*` two italics rather than one. A deliberate difference from the
// lookbehind version: in `*a**b*` the `*` that closes the first italic cannot
// also be the outer edge of a second, so only `*a*` is emphasis.
const ITALIC_STAR = /(^|\W)\*(\S(?:.*?\S)??)\*(?!\w)/g;
const ITALIC_UNDERSCORE = /(^|\W)_(\S(?:.*?\S)??)_(?!\w)/g;

function renderEmphasis(text, plain = false) {
  return text
    .replace(/\*\*(.+?)\*\*/g, plain ? '$1' : '<strong>$1</strong>')
    .replace(ITALIC_STAR, '$1<em>$2</em>')
    .replace(ITALIC_UNDERSCORE, '$1<em>$2</em>');
}

// `[label](url)`, with balanced parentheses in the url (Wikipedia-style
// addresses). Returns the text with every link replaced by `park(anchor)`.
function replaceMarkdownLinks(text, park, plain) {
  let out = '';
  let from = 0;
  const open = /\[([^\]]+)\]\(/g;
  for (let m = open.exec(text); m; m = open.exec(text)) {
    let depth = 1;
    let i = open.lastIndex;
    while (i < text.length && depth > 0) {
      if (text[i] === '(') depth += 1;
      else if (text[i] === ')') depth -= 1;
      i += 1;
    }
    if (depth > 0) continue; // never closed: plain text
    const link = resolveLink(text.slice(open.lastIndex, i - 1));
    out += text.slice(from, m.index);
    out += link ? park(anchor(link, renderEmphasis(m[1], plain))) : renderEmphasis(m[1], plain);
    from = i;
    open.lastIndex = i;
  }
  return out + text.slice(from);
}

// A bare address in running text: `https://…` or `www.…` after a word boundary.
// The sentence's own punctuation does not belong to it (`see www.x.cat.`), nor
// does a `)` it never opened, nor the `**` of bold around it.
function replaceBareUrls(text, park) {
  return text.replace(/\b(?:https?:\/\/|www\.)[^\s\0]+/gi, (found) => {
    let url = found;
    for (const stop of ['&lt;', '&gt;', '&quot;']) {
      const at = url.indexOf(stop);
      if (at !== -1) url = url.slice(0, at);
    }
    for (;;) {
      const last = url.slice(-1);
      const unopened = last === ')' && url.split('(').length < url.split(')').length;
      if (/[.,;:!?*]/.test(last) || unopened) url = url.slice(0, -1);
      else break;
    }
    const link = resolveLink(url);
    return link ? park(anchor(link, url)) + found.slice(url.length) : found;
  });
}

// `text` always arrives HTML-escaped from markdownToHtml, so nothing in here
// escapes again: doing so turned a `&` in a query string into `&amp;amp;`, and
// the browser then resolved the href with a literal `&amp;` inside it —
// `?a=1&b=2` became `?a=1&amp;b=2` and the link went somewhere else.
function renderInline(text, plain = false) {
  // Each generated anchor is parked behind a placeholder before the emphasis
  // passes run, so they cannot rewrite the inside of an href: a URL with a
  // `*…*` or `_…_` segment used to come back with an <em> spliced into it.
  // Restored at the end, untouched.
  const links = [];
  const park = (html) => {
    links.push(html);
    return `\0LINK${links.length - 1}\0`;
  };
  let result = replaceMarkdownLinks(text, park, plain);
  result = replaceBareUrls(result, park);
  result = renderEmphasis(result, plain);
  return result.replace(/\0LINK(\d+)\0/g, (match, i) => links[Number(i)] ?? match);
}

// GFM pipe-table line shapes. The separator row (|---|---|, optional colons)
// carries no escapable characters, so it can be tested on the raw line.
const isTableRow = (l) => /^\s*\|.*\|\s*$/.test(l);
const isTableSeparator = (l) => /^\s*\|(?:\s*:?-+:?\s*\|)+\s*$/.test(l);
const tableCells = (escapedLine) => {
  const trimmed = escapedLine.trim();
  return trimmed
    .slice(1, -1)
    .split('|')
    .map((c) => c.trim());
};

function markdownToHtml(text, headingBase = 3, variant = 'default') {
  if (!text) return '';
  const plain = variant === 'card';

  const lines = text.split(/\r?\n/);
  const output = [];
  let inUl = false;
  let inOl = false;

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const line = escapeHtml(rawLine);

    // Pipe table: a |header| row immediately followed by a |---| separator row.
    // Cells are escaped (via `line`) before splitting, then get inline rendering.
    if (isTableRow(rawLine) && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
      if (inUl) {
        output.push('</ul>');
        inUl = false;
      }
      if (inOl) {
        output.push('</ol>');
        inOl = false;
      }
      const header = tableCells(line)
        .map((c) => `<th>${renderInline(c, plain)}</th>`)
        .join('');
      const bodyRows = [];
      let j = i + 2;
      while (j < lines.length && isTableRow(lines[j]) && !isTableSeparator(lines[j])) {
        const cells = tableCells(escapeHtml(lines[j])).map(
          (c) => `<td>${renderInline(c, plain)}</td>`
        );
        bodyRows.push(`<tr>${cells.join('')}</tr>`);
        j++;
      }
      output.push(
        `<div class="markdown-table-wrap"><table><thead><tr>${header}</tr></thead>` +
          `<tbody>${bodyRows.join('')}</tbody></table></div>`
      );
      i = j - 1;
      continue;
    }

    // Heading: # / ## / ###+ text -> h{base} / h{base+1} / h{base+2} (capped).
    // The default base is 3 (a bio inside a page that already owns h1/h2);
    // a page whose markdown IS the content (LegalPage) passes base 2 so the
    // outline doesn't skip a level (axe heading-order).
    // Up to three spaces may precede the `#`s and a closing sequence of `#`s
    // (`## Horario ##`) is not part of the title. `#Normas`, with no space, stays
    // text: otherwise `#arduino #maker` would be a heading.
    const headingMatch = line.match(/^ {0,3}(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$/);
    if (headingMatch) {
      if (inUl) {
        output.push('</ul>');
        inUl = false;
      }
      if (inOl) {
        output.push('</ol>');
        inOl = false;
      }
      // On a card a title is one line of ordinary text: the card has its own
      // <h3>, and a description cannot put headings in the page's outline.
      if (plain) {
        output.push(`<span>${renderInline(headingMatch[2], plain)}</span>`);
        continue;
      }
      const tag = `h${Math.min(headingMatch[1].length, 3) + headingBase - 1}`;
      output.push(`<${tag}>${renderInline(headingMatch[2])}</${tag}>`);
      continue;
    }

    // Unordered list: - text, * text or + text
    const ulMatch = line.match(/^[-*+] (.+)$/);
    if (ulMatch) {
      if (inOl) {
        output.push('</ol>');
        inOl = false;
      }
      if (!inUl) {
        output.push('<ul>');
        inUl = true;
      }
      output.push(`<li>${renderInline(ulMatch[1], plain)}</li>`);
      continue;
    }

    // Ordered list: 1. text
    const olMatch = line.match(/^\d+\. (.+)$/);
    if (olMatch) {
      if (inUl) {
        output.push('</ul>');
        inUl = false;
      }
      if (!inOl) {
        output.push('<ol>');
        inOl = true;
      }
      output.push(`<li>${renderInline(olMatch[1], plain)}</li>`);
      continue;
    }

    // Close any open list
    if (inUl) {
      output.push('</ul>');
      inUl = false;
    }
    if (inOl) {
      output.push('</ol>');
      inOl = false;
    }

    if (line.trim() === '') {
      output.push('<br/>');
    } else {
      output.push(`<span>${renderInline(line, plain)}</span>`);
    }
  }

  if (inUl) output.push('</ul>');
  if (inOl) output.push('</ol>');

  return output.join('');
}

// eslint-disable-next-line react-refresh/only-export-components -- pure helpers co-located for unit tests (markdown.test.jsx) and reuse (sanitizeUrl on ThingPage)
export { markdownToHtml, sanitizeUrl };

function Markdown({ text, className, headingBase, variant, navigate }) {
  const html = markdownToHtml(text, headingBase, variant);
  // A link to this site is followed by the router — no reload — but only on a
  // plain left click: cmd/ctrl/shift/alt and the middle button stay the
  // browser's, as with `ButtonLink`.
  const follow = (event) => {
    if (!navigate || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest?.('a[data-internal]');
    if (!link || !event.currentTarget.contains(link)) return;
    event.preventDefault();
    navigate(link.getAttribute('href'));
  };
  return (
    // The container only listens for clicks that bubble up from real links.
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions, jsx-a11y/click-events-have-key-events -- a keyboard activates the <a> itself, and its click bubbles here
    <div
      className={`markdown-text ${className}`.trim()}
      onClick={follow}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

function RoutedMarkdown(props) {
  return <Markdown {...props} navigate={useNavigate()} />;
}

export default function MarkdownText({ text, className = '', headingBase = 3, variant }) {
  const routed = useInRouterContext();
  if (!text) return null;
  const Component = routed ? RoutedMarkdown : Markdown;
  return (
    <Component text={text} className={className} headingBase={headingBase} variant={variant} />
  );
}

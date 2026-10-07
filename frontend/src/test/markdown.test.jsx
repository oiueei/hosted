import { readFileSync } from 'node:fs';
import { describe, test, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router';
import MarkdownText, { markdownToHtml } from '../components/MarkdownText';

describe('markdownToHtml', () => {
  test('renders bold text', () => {
    expect(markdownToHtml('Hello **world**')).toContain('<strong>world</strong>');
  });

  test('renders italic with asterisks', () => {
    expect(markdownToHtml('Hello *world*')).toContain('<em>world</em>');
  });

  test('renders italic with underscores', () => {
    expect(markdownToHtml('Hello _world_')).toContain('<em>world</em>');
  });

  test('renders links with safe URLs', () => {
    const result = markdownToHtml('[Click here](https://example.com)');
    expect(result).toContain('href="https://example.com"');
    expect(result).toContain('>Click here</a>');
  });

  test('a query string survives with one ampersand, not an escaped one', () => {
    // The line is HTML-escaped before link parsing, so escaping the URL a
    // second time produced `&amp;amp;` — which the browser then resolves to a
    // literal `&amp;` in the href, sending the reader to a different URL than
    // the owner wrote. Owner descriptions and user bios are full of such links.
    const result = markdownToHtml('[Docs](https://example.com/?a=1&b=2)');
    expect(result).toContain('href="https://example.com/?a=1&amp;b=2"');
    expect(result).not.toContain('&amp;amp;');
  });

  test('an asterisk inside a URL is not turned into emphasis', () => {
    // The bold/italic passes run over the whole string after links are built,
    // so an unprotected href could come back with an <em> spliced into it.
    const result = markdownToHtml('[Photo](https://example.com/a/*b*/c)');
    expect(result).toContain('href="https://example.com/a/*b*/c"');
    expect(result).not.toContain('<em>');
  });

  test('emphasis around a link still renders, and the link stays intact', () => {
    // The placeholder must not cost us the ordinary case.
    const result = markdownToHtml('**See [the docs](https://example.com) now**');
    expect(result).toContain('<strong>');
    expect(result).toContain('href="https://example.com"');
    expect(result).toContain('>the docs</a>');
  });

  test('a link label keeps its ampersand readable', () => {
    const result = markdownToHtml('[Tom & Jerry](https://example.com)');
    // Escaped exactly once: renders as "Tom & Jerry", not "Tom &amp; Jerry".
    expect(result).toContain('>Tom &amp; Jerry</a>');
    expect(result).not.toContain('&amp;amp;');
  });

  test('user text cannot forge a link placeholder', () => {
    // Links are parked behind NUL-delimited markers while emphasis is applied.
    // NUL is stripped by the escaper so typed text can never mint one and pull
    // in another link — or an undefined slot.
    const result = markdownToHtml('\0LINK0\0 plain text');
    expect(result).not.toContain('<a ');
    expect(result).not.toContain('undefined');
  });

  test('a javascript: target is no link: the label shows as text', () => {
    const result = markdownToHtml('[Click](javascript:alert(1))');
    expect(result).not.toContain('<a');
    expect(result).not.toContain('javascript:');
    expect(result).toContain('Click');
  });

  test('a data: target is no link either', () => {
    const result = markdownToHtml('[Click](data:text/html,<h1>XSS</h1>)');
    expect(result).not.toContain('<a');
    expect(result).not.toContain('href');
    expect(result).toContain('Click');
  });

  test('renders unordered lists', () => {
    const result = markdownToHtml('- Item one\n- Item two');
    expect(result).toContain('<ul>');
    expect(result).toContain('<li>Item one</li>');
    expect(result).toContain('<li>Item two</li>');
    expect(result).toContain('</ul>');
  });

  test('renders ordered lists', () => {
    const result = markdownToHtml('1. First\n2. Second');
    expect(result).toContain('<ol>');
    expect(result).toContain('<li>First</li>');
    expect(result).toContain('<li>Second</li>');
    expect(result).toContain('</ol>');
  });

  test('escapes HTML tags in input', () => {
    const result = markdownToHtml('<script>alert("xss")</script>');
    expect(result).not.toContain('<script>');
    expect(result).toContain('&lt;script&gt;');
  });

  test('handles nested bold and italic', () => {
    const result = markdownToHtml('**bold *italic* bold**');
    expect(result).toContain('<strong>');
    expect(result).toContain('<em>italic</em>');
  });

  test('handles empty input', () => {
    expect(markdownToHtml('')).toBe('');
    expect(markdownToHtml(null)).toBe('');
    expect(markdownToHtml(undefined)).toBe('');
  });

  test('handles plain text without markdown', () => {
    const result = markdownToHtml('Just plain text');
    expect(result).toContain('Just plain text');
    expect(result).not.toContain('<strong>');
    expect(result).not.toContain('<em>');
  });

  test('handles mixed lists and text', () => {
    const result = markdownToHtml('Header\n- Item\nFooter');
    expect(result).toContain('<ul>');
    expect(result).toContain('<li>Item</li>');
    expect(result).toContain('</ul>');
    expect(result).toContain('Header');
    expect(result).toContain('Footer');
  });

  test('renders pipe tables with a scroll wrapper', () => {
    const result = markdownToHtml(
      '| Día | Horario |\n|---|---|\n| Lunes - Viernes | 09:00 - 14:00 |\n| Domingo | Cerrado |'
    );
    expect(result).toContain('class="markdown-table-wrap"');
    expect(result).toContain('<table><thead><tr><th>Día</th><th>Horario</th></tr></thead>');
    expect(result).toContain('<td>Lunes - Viernes</td>');
    expect(result).toContain('<td>Domingo</td><td>Cerrado</td>');
  });

  test('table cells render inline markdown and stay HTML-escaped', () => {
    const result = markdownToHtml('| A | B |\n|---|---|\n| **bold** | <script>alert(1)</script> |');
    expect(result).toContain('<td><strong>bold</strong></td>');
    expect(result).not.toContain('<script>');
    expect(result).toContain('&lt;script&gt;');
  });

  test('a pipe line without a separator row is not a table', () => {
    const result = markdownToHtml('| just | text |\nplain line');
    expect(result).not.toContain('<table>');
    expect(result).toContain('| just | text |');
  });

  test('text after a table resumes normal rendering', () => {
    const result = markdownToHtml('| A |\n|---|\n| x |\nAfter');
    expect(result).toContain('</table></div>');
    expect(result).toContain('<span>After</span>');
  });

  test('renders # / ## / ### as h3 / h4 / h5', () => {
    expect(markdownToHtml('# Título')).toBe('<h3>Título</h3>');
    expect(markdownToHtml('## Título')).toBe('<h4>Título</h4>');
    expect(markdownToHtml('### Título')).toBe('<h5>Título</h5>');
  });

  test('deeper heading levels cap at h5', () => {
    expect(markdownToHtml('#### Título')).toBe('<h5>Título</h5>');
    expect(markdownToHtml('###### Título')).toBe('<h5>Título</h5>');
  });

  test('a heading escapes HTML and still renders inline markdown', () => {
    const result = markdownToHtml('# **Bold** <script>alert(1)</script>');
    expect(result).toBe('<h3><strong>Bold</strong> &lt;script&gt;alert(1)&lt;/script&gt;</h3>');
    expect(result).not.toContain('<script>');
  });

  test('a heading between paragraphs does not disturb the surrounding text', () => {
    const result = markdownToHtml('Before\n## Título\nAfter');
    expect(result).toBe('<span>Before</span><h4>Título</h4><span>After</span>');
  });

  test('a heading closes an open list', () => {
    const result = markdownToHtml('- Item\n# Título');
    expect(result).toBe('<ul><li>Item</li></ul><h3>Título</h3>');
  });

  test('a bare # with no text is not treated as a heading', () => {
    const result = markdownToHtml('#');
    expect(result).not.toContain('<h3>');
    expect(result).toContain('#');
  });
});

describe('MarkdownText component', () => {
  test('renders null for empty text', () => {
    const { container } = render(<MarkdownText text="" />);
    expect(container.innerHTML).toBe('');
  });

  test('renders markdown content', () => {
    const { container } = render(<MarkdownText text="**Hello** world" />);
    expect(container.querySelector('strong').textContent).toBe('Hello');
  });

  test('applies className prop', () => {
    const { container } = render(<MarkdownText text="Test" className="custom" />);
    expect(container.querySelector('.markdown-text.custom')).toBeTruthy();
  });
});

// Links, as an owner writes them: bare, with parentheses, without a scheme, to the
// site itself, to a mailbox. What is never allowed is a script.
describe('markdownToHtml — links', () => {
  const html = markdownToHtml;

  test('a bare address is linked and reads as it was typed', () => {
    const out = html('Mira https://example.com/a?b=1&c=2 ahora');
    expect(out).toContain(
      '<a href="https://example.com/a?b=1&amp;c=2" target="_blank" rel="noopener noreferrer">https://example.com/a?b=1&amp;c=2</a>'
    );
  });

  test('a bare www. address is linked as https and shows what was typed', () => {
    const out = html('Web: www.x.cat');
    expect(out).toContain('href="https://www.x.cat"');
    expect(out).toContain('>www.x.cat</a>');
  });

  test.each([
    ['See https://x.com.', 'https://x.com'],
    ['See https://x.com, ok', 'https://x.com'],
    ['Is it https://x.com?', 'https://x.com'],
    ['(see https://x.com)', 'https://x.com'],
    ['**https://x.com**', 'https://x.com'],
  ])('punctuation around %s is not part of the address', (text, url) => {
    const out = html(text);
    expect(out).toContain(`href="${url}"`);
    expect(out).toContain(`>${url}</a>`);
  });

  test('a ) the address opened itself stays in it', () => {
    const url = 'https://es.wikipedia.org/wiki/Foo_(bar)';
    expect(html(`Ver ${url}`)).toContain(`href="${url}"`);
  });

  test('a bare address is parked: _ and * inside it never become emphasis', () => {
    const out = html('https://example.com/a_b_c/*d*/e_f_');
    expect(out).not.toContain('<em>');
    expect(out).toContain('href="https://example.com/a_b_c/*d*/e_f_"');
  });

  test('[text](url) takes balanced parentheses in the url', () => {
    const url = 'https://es.wikipedia.org/wiki/Foo_(bar)';
    const out = html(`[wiki](${url}) y más`);
    expect(out).toContain(`href="${url}"`);
    expect(out).toContain('>wiki</a> y más');
  });

  test('[text](www.…) has no scheme to lose: it becomes https', () => {
    const out = html('[web](www.x.cat)');
    expect(out).toContain('href="https://www.x.cat"');
    expect(out).not.toContain('href="www.x.cat"');
  });

  test('mailto: is a link, in the same tab', () => {
    const out = html('[escríbeme](mailto:lala@example.com)');
    expect(out).toContain('<a href="mailto:lala@example.com">escríbeme</a>');
  });

  test('a label may carry bold and italics', () => {
    const out = html('[**gran** _web_](https://example.com)');
    expect(out).toContain('<strong>gran</strong> <em>web</em></a>');
  });

  test('a target that is not http(s), mailto or a site path is only its label', () => {
    for (const target of [
      'foo/bar',
      '//evil.example',
      '#top',
      'ftp://x.org',
      'javascript:alert(1)',
    ]) {
      const out = html(`[label](${target})`);
      expect(out, target).not.toContain('<a');
      expect(out, target).toContain('label');
    }
  });

  test('a [text](url never closed is not a [text] link', () => {
    const out = html('[a](https://x.com');
    expect(out).toContain('[a](');
    expect(out).not.toContain('>a</a>');
  });

  test('a site path is internal: same tab, marked for the router', () => {
    const out = html('[la colección](/collections/ABC123?x=1&y=2)');
    expect(out).toContain('<a href="/collections/ABC123?x=1&amp;y=2" data-internal>');
    expect(out).not.toContain('target=');
  });

  test('an absolute address of this very site is reduced to its path', () => {
    const out = html(`[aquí](${window.location.origin}/me?x=1#top)`);
    expect(out).toContain('<a href="/me?x=1#top" data-internal>aquí</a>');
    expect(out).not.toContain('target=');
  });

  test('another site is external: a new tab, no opener', () => {
    const out = html('[otra](https://elsewhere.example/x)');
    expect(out).toContain('target="_blank" rel="noopener noreferrer"');
    expect(out).not.toContain('data-internal');
  });
});

describe('MarkdownText — following a link to this site', () => {
  function Where() {
    return <div data-testid="where">{useLocation().pathname}</div>;
  }
  const renderIn = (text) =>
    render(
      <MemoryRouter initialEntries={['/start']}>
        <Routes>
          <Route path="*" element={<Where />} />
        </Routes>
        <MarkdownText text={text} />
      </MemoryRouter>
    );

  test('a plain left click navigates with the router, not the browser', () => {
    renderIn('[mi grupo](/collections/ABC123)');
    const link = screen.getByRole('link', { name: 'mi grupo' });

    const notPrevented = fireEvent.click(link);

    expect(notPrevented).toBe(false);
    expect(screen.getByTestId('where')).toHaveTextContent('/collections/ABC123');
  });

  test.each([['metaKey'], ['ctrlKey'], ['shiftKey'], ['altKey']])(
    'a click with %s stays the browser’s',
    (modifier) => {
      renderIn('[mi grupo](/collections/ABC123)');

      const notPrevented = fireEvent.click(screen.getByRole('link', { name: 'mi grupo' }), {
        [modifier]: true,
      });

      expect(notPrevented).toBe(true);
      expect(screen.getByTestId('where')).toHaveTextContent('/start');
    }
  );

  test('the middle button stays the browser’s', () => {
    renderIn('[mi grupo](/collections/ABC123)');

    const notPrevented = fireEvent.click(screen.getByRole('link', { name: 'mi grupo' }), {
      button: 1,
    });

    expect(notPrevented).toBe(true);
    expect(screen.getByTestId('where')).toHaveTextContent('/start');
  });

  test('an external link is left alone', () => {
    renderIn('[otra](https://elsewhere.example)');

    const notPrevented = fireEvent.click(screen.getByRole('link', { name: 'otra' }));

    expect(notPrevented).toBe(true);
    expect(screen.getByTestId('where')).toHaveTextContent('/start');
  });

  test('outside a router it still renders, and an internal link is an ordinary one', () => {
    render(<MarkdownText text="[mi grupo](/collections/ABC123)" />);

    const link = screen.getByRole('link', { name: 'mi grupo' });
    expect(link).toHaveAttribute('href', '/collections/ABC123');
    expect(fireEvent.click(link)).toBe(true);
  });
});

describe('markdownToHtml — headings', () => {
  test('the closing sequence is not part of the title', () => {
    expect(markdownToHtml('## Horario ##')).toBe('<h4>Horario</h4>');
    expect(markdownToHtml('# Horario #####  ')).toBe('<h3>Horario</h3>');
  });

  test('a # that is part of the title stays', () => {
    expect(markdownToHtml('# Aprende C#')).toBe('<h3>Aprende C#</h3>');
  });

  test('up to three spaces may precede the #', () => {
    expect(markdownToHtml('   ## Horario')).toBe('<h4>Horario</h4>');
  });

  test('four spaces are not a title, nor is a # glued to its word', () => {
    expect(markdownToHtml('    ## Horario')).not.toContain('<h');
    expect(markdownToHtml('#Normas')).toBe('<span>#Normas</span>');
    expect(markdownToHtml('#arduino #maker')).not.toContain('<h');
  });
});

describe('markdownToHtml — lists, emphasis and line breaks', () => {
  test.each([['-'], ['*'], ['+']])('a "%s " line is a bullet', (mark) => {
    expect(markdownToHtml(`${mark} uno\n${mark} dos`)).toBe('<ul><li>uno</li><li>dos</li></ul>');
  });

  test('bullets with different marks are one list', () => {
    expect(markdownToHtml('- a\n* b\n+ c')).toBe('<ul><li>a</li><li>b</li><li>c</li></ul>');
  });

  test('a * with no space after it is not a bullet', () => {
    expect(markdownToHtml('*uno*')).toBe('<span><em>uno</em></span>');
  });

  test('an asterisk glued to the word inside is italics', () => {
    expect(markdownToHtml('*así* y *otra cosa*')).toBe(
      '<span><em>así</em> y <em>otra cosa</em></span>'
    );
  });

  test('2 * 3 * 4 is arithmetic, not italics', () => {
    const out = markdownToHtml('Son 2 * 3 * 4 piezas');
    expect(out).not.toContain('<em>');
    expect(out).toContain('2 * 3 * 4');
  });

  test('the closing mark must be glued to the word too', () => {
    expect(markdownToHtml('un *error * grave')).not.toContain('<em>');
    expect(markdownToHtml('un _error _ grave')).not.toContain('<em>');
  });

  test('the same rule holds for underscores', () => {
    expect(markdownToHtml('_así_')).toBe('<span><em>así</em></span>');
    expect(markdownToHtml('a _ b _ c')).not.toContain('<em>');
  });

  // The italics are written without lookbehind (Safari < 16.4 cannot parse it):
  // the outer edge is captured and given back. These are the shapes where that
  // rewrite could read differently from the rule it replaced.
  test.each([
    ['*a* y *b*', '<span><em>a</em> y <em>b</em></span>'],
    ['*a *b*', '<span><em>a *b</em></span>'],
    ['(*a*)', '<span>(<em>a</em>)</span>'],
    ['*a*.', '<span><em>a</em>.</span>'],
    ['_a_b', '<span>_a_b</span>'],
    ['a*b*c', '<span>a*b*c</span>'],
    ['a*b* c', '<span>a*b* c</span>'],
  ])('italics: %s', (input, expected) => {
    expect(markdownToHtml(input)).toBe(expected);
  });

  test('a closing mark is not also the outer edge of the next italic', () => {
    // The one case that differs from the lookbehind version, which gave
    // <em>a</em><em>b</em>: accepted, and pinned so it stays a decision.
    expect(markdownToHtml('*a**b*')).toBe('<span><em>a</em>*b*</span>');
  });

  test('an italic right after a link keeps the link whole', () => {
    expect(markdownToHtml('[x](https://e.com)*a*')).toBe(
      '<span><a href="https://e.com" target="_blank" rel="noopener noreferrer">x</a><em>a</em></span>'
    );
  });

  test('Windows line breaks do not break headings, lists or tables', () => {
    const out = markdownToHtml(
      '## Horario\r\n- lunes\r\n- martes\r\n| a | b |\r\n|---|---|\r\n| 1 | 2 |'
    );
    expect(out).toContain('<h4>Horario</h4>');
    expect(out).toContain('<ul><li>lunes</li><li>martes</li></ul>');
    expect(out).toContain('<table>');
    expect(out).not.toContain('\r');
  });
});

// Shared with the email note's engine (core/tests/unit/test_email_note.py): the
// two renderers of `[text](url)` must read every target alike, or an owner's link
// works in the app and not in the email, or the other way round.
describe('markdownToHtml — the cases shared with the email engine', () => {
  const { cases } = JSON.parse(readFileSync('src/test/markdownLinkParity.json', 'utf8'));

  test.each(cases.map((c) => [c.input, c.href]))('%s -> %s', (input, href) => {
    const holder = document.createElement('div');
    holder.innerHTML = markdownToHtml(input);
    expect(holder.querySelector('a')?.getAttribute('href') ?? null).toBe(href);
  });
});

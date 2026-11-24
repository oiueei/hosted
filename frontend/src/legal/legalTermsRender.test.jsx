import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, test, expect } from 'vitest';
import MarkdownText from '../components/MarkdownText';
import es from './es';
import ca from './ca';
import en from './en';

// The terms are an ordered list that `MarkdownText` draws; it has no nested lists, so a
// term with sub-points must stay on its own line or the list is cut in two and the next
// term restarts at 1. This reads the page as it is drawn, not the Markdown.
const LANGS = { es, ca, en };
const LAW = { es: 'Ley y fuero.', ca: 'Llei i fur.', en: 'Law and venue.' };
const NINE = {
  es: 'Si tu biblioteca pide datos para prestar.',
  ca: 'Si la teva biblioteca demana dades per prestar.',
  en: 'If your library asks for details in order to lend.',
};

function termsList(lang) {
  const { container } = render(
    <MemoryRouter>
      <MarkdownText text={LANGS[lang]} headingBase={2} />
    </MemoryRouter>
  );
  return [...container.querySelectorAll('ol')].find((ol) => ol.textContent.includes(LAW[lang]));
}

describe('the terms as /legal draws them', () => {
  test.each(Object.keys(LANGS))('%s: one list of ten, the library term ninth, law last', (lang) => {
    const list = termsList(lang);
    const items = [...list.children];

    expect(items).toHaveLength(10);
    expect(items[8].textContent).toContain(NINE[lang]);
    expect(items[9].textContent).toContain(LAW[lang]);
    expect(list.querySelector('ul, ol')).toBeNull();
  });
});

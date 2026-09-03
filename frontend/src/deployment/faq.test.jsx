import { render, screen, waitFor } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';
import i18n from 'i18next';

import './testI18n';
import App from '../App';
import { loadFaqEntries } from './faq';
import faqEs from './faq/es';
import faqCa from './faq/ca';
import faqEn from './faq/en';

/**
 * The help page, and the promises its shape exists to keep.
 *
 * A question without its own anchor cannot be pasted into a chat; a placeholder
 * that ships reads as a fact to whoever finds it; an answer added to one
 * language and forgotten in the other two leaves readers of those languages
 * with a page that is quietly missing something. All three fail silently, which
 * is why they are pinned here rather than left to a proofread.
 */

expect.extend(toHaveNoViolations);

const LANGUAGES = [
  ['es', faqEs],
  ['ca', faqCa],
  ['en', faqEn],
];

window.scrollTo = vi.fn();
globalThis.fetch = vi.fn(() =>
  Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({}) })
);

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

afterEach(async () => {
  await i18n.changeLanguage('en');
});

describe('the app serves the help page', () => {
  test('/faq answers with the questions and not with the 404 page', async () => {
    window.history.pushState({}, '', '/faq');
    render(<App />);

    expect(await screen.findByRole('heading', { name: faqEn[0].q, level: 2 })).toBeInTheDocument();
    await waitFor(() => expect(document.title).toMatch(/frequently asked questions/i));
  });

  test('a Catalan reader gets the Catalan answers, not the English ones', async () => {
    await i18n.changeLanguage('ca');
    window.history.pushState({}, '', '/faq');
    render(<App />);

    expect(await screen.findByRole('heading', { name: faqCa[0].q, level: 2 })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: faqEn[0].q, level: 2 })).toBeNull();
  });

  test('every question is an anchor somebody can link to', async () => {
    window.history.pushState({}, '', '/faq');
    render(<App />);

    await screen.findByRole('heading', { name: faqEn[0].q, level: 2 });

    for (const entry of faqEn) {
      const heading = document.getElementById(entry.id);
      expect(heading, `no anchor for "${entry.id}"`).not.toBeNull();
      expect(heading.tagName).toBe('H2');
      expect(heading.textContent).toBe(entry.q);
    }
  });

  test('a destination inside the app stays inside the app', async () => {
    window.history.pushState({}, '', '/faq');
    render(<App />);

    await screen.findByRole('heading', { name: faqEn[0].q, level: 2 });

    // `MarkdownText` opens every anchor it renders in a new tab, which is why
    // these live in their own field. If one ever migrates into the Markdown,
    // this is what notices: /legal would start opening in a second window.
    const internal = faqEn.filter((entry) => entry.link);
    expect(internal.length).toBeGreaterThan(0);
    for (const { link } of internal) {
      const anchor = document.querySelector(`a[href="${link.to}"]`);
      expect(anchor, `no in-app link to ${link.to}`).not.toBeNull();
      expect(anchor.getAttribute('target')).toBeNull();
    }
  });

  test('the page has no accessibility violations', async () => {
    window.history.pushState({}, '', '/faq');
    const { container } = render(<App />);

    await screen.findByRole('heading', { name: faqEn[0].q, level: 2 });

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe('the three languages stay one page', () => {
  test('same questions, same order, same anchors', () => {
    const ids = faqEs.map((entry) => entry.id);
    for (const [lang, entries] of LANGUAGES) {
      expect(
        entries.map((entry) => entry.id),
        `${lang} drifted from es`
      ).toEqual(ids);
    }
  });

  test('a question that links somewhere links there in every language', () => {
    for (const [index, entry] of faqEs.entries()) {
      for (const [lang, entries] of LANGUAGES) {
        expect(entries[index].link?.to, `${lang}/${entry.id} disagrees on the destination`).toBe(
          entry.link?.to
        );
      }
    }
  });

  test('every answer is written, in every language', () => {
    for (const [lang, entries] of LANGUAGES) {
      for (const entry of entries) {
        expect(`${entry.q} ${entry.a}`, `${lang}/${entry.id}`).not.toMatch(/\{\{|TODO|TBD|XXX/);
        expect(entry.q.length, `${lang}/${entry.id} has no question`).toBeGreaterThan(0);
        expect(entry.a.length, `${lang}/${entry.id} has no answer`).toBeGreaterThan(0);
      }
    }
  });

  test('the ids are unique, because they are public URLs', () => {
    const ids = faqEs.map((entry) => entry.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  test('each language loads its own answers, and an unknown one falls back', async () => {
    for (const [lang, entries] of LANGUAGES) {
      await expect(loadFaqEntries(lang)).resolves.toBe(entries);
    }
    await expect(loadFaqEntries('pt')).resolves.toBe(faqEn);
  });
});

describe('the ways in', () => {
  // Four doors were asked for; three are here. The fourth — a line under the
  // form on /popin — would need `MagicLinkJoinPage` to accept a footer slot,
  // and that component is upstream's. See the note in the commit.
  test('/login offers it, which is what faqPath is for', async () => {
    window.history.pushState({}, '', '/login');
    render(<App />);

    await waitFor(() => expect(document.querySelector('a[href="/faq"]')).not.toBeNull());
  });

  test('/welcome offers it, where somebody already inside asks', async () => {
    window.history.pushState({}, '', '/welcome');
    render(<App />);

    await waitFor(() => expect(document.querySelector('a[href="/faq"]')).not.toBeNull());
  });

  test('/legal offers it, and says which of the two is binding', async () => {
    window.history.pushState({}, '', '/legal');
    render(<App />);

    // Written inside the legal Markdown, so `MarkdownText` renders it — which
    // means this one *does* open in a new tab, unlike the links on the help
    // page itself. Deliberate here: a reader sent to the plain-language answer
    // keeps the full text open behind them.
    const link = await waitFor(() => {
      const found = document.querySelector('a[href="/faq"]');
      expect(found).not.toBeNull();
      return found;
    });
    expect(link.getAttribute('target')).toBe('_blank');
  });
});

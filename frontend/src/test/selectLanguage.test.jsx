import { render, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ mode: 'PROPRIETARY' }) })
  ),
  extractApiError: vi.fn(() => Promise.resolve('')),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import AddThingPage from '../pages/AddThingPage';

/**
 * HDS ships its own assistive wording for `Select` — "choose one", "2 selected
 * options", "clear current selection" — and it defaults to **Finnish**. Every
 * Select in this app therefore says which language it wants.
 *
 * In HDS 5 that was the `language` prop, and `frontend/CLAUDE.md` still said so.
 * HDS 6 moved it inside `texts`, and it did not warn: the prop is simply
 * ignored, the component renders, the page looks right, and the only thing that
 * changed is what a screen reader reads out. Fourteen Selects were announcing
 * themselves in Finnish to readers of Spanish, Catalan and English — and no axe
 * rule catches it, because none of them compares the language of an
 * `aria-label` with the language of the page.
 *
 * `language="en"` is still correct on `DateInput` and `Accordion`, which do
 * honour it; this is a `Select` bug, not a repo-wide one.
 */
const FINNISH = /valitse|valittu|valittua|poista nykyinen/i;

describe('no Select speaks Finnish', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('userCode', 'ABC123');
  });

  test('the thing form announces its selects in the language it was given', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/collections/COL001/add']}>
        <Routes>
          <Route path="/collections/:code/add" element={<AddThingPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() =>
      expect(container.querySelector('#add-thing-type-main-button')).toBeTruthy()
    );

    const labels = [...container.querySelectorAll('[aria-label]')].map((el) =>
      el.getAttribute('aria-label')
    );
    expect(labels.filter((l) => FINNISH.test(l))).toEqual([]);
    // Not vacuous: these *are* HDS's own assistive strings, in English.
    expect(labels.some((l) => /selected option/i.test(l))).toBe(true);
  });
});

/**
 * The render above covers one form. This is the guard for the other thirteen:
 * the failure is invisible on screen, so a Select added tomorrow with the old
 * prop would look perfectly fine in review and in every axe scan.
 */
describe('the dead prop does not come back', () => {
  function jsxFiles(dir, found = []) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) jsxFiles(full, found);
      else if (entry.name.endsWith('.jsx') && !entry.name.includes('.test.')) found.push(full);
    }
    return found;
  }

  test('no <Select> passes `language` as a prop', () => {
    // Vitest runs from the frontend root, so `src` resolves; a wrong cwd throws
    // here rather than quietly sweeping nothing.
    const files = jsxFiles('src');
    expect(files.length).toBeGreaterThan(20);

    const offenders = [];
    for (const file of files) {
      const source = fs.readFileSync(file, 'utf8');
      // Each <Select …> element, up to the `/>` that closes it.
      for (const element of source.match(/<Select[\s\S]*?\/>/g) || []) {
        if (/^\s*language=/m.test(element)) {
          offenders.push(file);
        }
      }
    }

    expect(offenders).toEqual([]);
  });

  /**
   * The companion to the test above. That one catches `language` passed as a
   * *prop* (silently ignored since HDS 6); this one catches the mapping being
   * written out by hand at a call site instead of going through `hdsLang`.
   *
   * It is here because that drift really happened: `ShareCollectionMenu` carried
   * its own `i18n.language?.startsWith('fi') ? 'fi' : 'en'`, which had already
   * diverged from the shared util — it sent Swedish to English. Found in the
   * 2026-08 frontend review, by reading, not by a failing test.
   *
   * A bare `language: 'en'` counts as hand-rolled too, and thirteen call sites
   * had one. Correct today, because every language OIUEEI offers maps to English
   * — and wrong the moment anyone adds Finnish or Swedish, which are the two
   * languages HDS actually ships strings for and the exact case `hdsLang` exists
   * to pass through. That is the bug from "Stop fourteen selects announcing
   * themselves in Finnish" waiting to happen again from the other direction.
   */
  test('no call site hand-rolls the HDS language mapping', () => {
    const files = jsxFiles('src');
    expect(files.length).toBeGreaterThan(20);

    const offenders = [];
    for (const file of files) {
      if (file.endsWith('hdsLang.js')) continue;
      const source = fs.readFileSync(file, 'utf8');
      for (const match of source.match(/language:\s*[^,\n}]+/g) || []) {
        if (!/hdsLang\(/.test(match)) offenders.push(`${file} → ${match.trim()}`);
      }
    }

    expect(offenders).toEqual([]);
  });
});

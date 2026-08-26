import { render, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import UserPage from '../pages/UserPage';

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

// The ordinary state of an account that arrived by magic link or invitation and
// never filled in a profile: `get_or_create(email=…)` leaves `name` empty, which
// is the whole argument of `8ff8737`. So this is not an exotic profile.
const NAMELESS = { code: 'OTH001', name: '', created: '2026-01-01', shared_collections: [] };

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ME0001');
  vi.clearAllMocks();
  apiFetch.mockImplementation((url) =>
    url.startsWith('/api/v1/invited-collections/') ? ok([]) : ok(NAMELESS)
  );
});

const renderNameless = () =>
  render(
    <MemoryRouter initialEntries={['/OTH001']}>
      <Routes>
        <Route path="/:userCode" element={<UserPage />} />
      </Routes>
    </MemoryRouter>
  );

/**
 * `UserPage`'s document title when the profile has no name.
 *
 * `titles.user` interpolates a name, so the page needs a word when there isn't
 * one. Until `de0e672` that word was the string literal `'Profile'`, on both
 * branches of a ternary — the one piece of copy on the page that never went
 * through i18n, so a Spanish or Catalan reader got an English browser tab and no
 * way to tell it was a default rather than a translation.
 *
 * The branch is easy to regress precisely because it is invisible in the
 * language the author works in: in English the literal and the translation are
 * the same word, so `en` alone cannot tell the two apart. That is why the
 * second half of this test is the one that matters.
 */
describe('UserPage — the title of a profile with no name', () => {
  afterEach(async () => {
    const { default: i18n } = await import('../i18n');
    await i18n.changeLanguage('en');
  });

  test('falls back to a translated word, not to an English literal', async () => {
    const { default: i18n } = await import('../i18n');
    await i18n.changeLanguage('en');

    renderNameless();
    await waitFor(() => expect(document.title).toBe('Profile — OIUEEI'));

    // The assertion the literal survived: in English it read correctly all along.
    await i18n.changeLanguage('es');
    await waitFor(() => expect(document.title).toBe('Perfil — OIUEEI'));

    await i18n.changeLanguage('ca');
    await waitFor(() => expect(document.title).toBe('Perfil — OIUEEI'));
  });
});

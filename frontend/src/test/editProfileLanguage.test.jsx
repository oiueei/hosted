import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
  ),
  extractApiError: vi.fn(() => Promise.resolve('')),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import * as capabilities from '../hooks/useCapabilities';
import i18n from '../i18n';
import EditProfilePage from '../pages/EditProfilePage';

const PROFILE = { name: 'Original name', headline: '', about: '', language: 'ca' };

function mockResponse(data, ok = true) {
  return { ok, status: ok ? 200 : 400, json: () => Promise.resolve(data) };
}

function setApi() {
  apiFetch.mockImplementation((url) => {
    if (url === '/api/v1/auth/me/') return Promise.resolve(mockResponse(PROFILE));
    if (url === '/api/v1/theeemes/') return Promise.resolve(mockResponse([]));
    return Promise.resolve(mockResponse({}));
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/me/edit']}>
      <Routes>
        <Route path="/me/edit" element={<EditProfilePage />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(async () => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ABC123');
  vi.clearAllMocks();
  setApi();
  // The first test in this file switches the live i18n singleton to Spanish
  // and leaves it there — reset so later tests don't depend on run order.
  await i18n.changeLanguage('en');
});

describe('EditProfilePage language Select (S7)', () => {
  test('changing language fetches the profile once and keeps unsaved edits', async () => {
    renderPage();

    const nameInput = await screen.findByDisplayValue('Original name');
    // Edit an unsaved field before touching the language Select.
    fireEvent.change(nameInput, { target: { value: 'Edited name' } });
    expect(screen.getByDisplayValue('Edited name')).toBeInTheDocument();

    const callsBeforeLanguageChange = apiFetch.mock.calls.filter(
      ([url]) => url === '/api/v1/auth/me/'
    ).length;
    expect(callsBeforeLanguageChange).toBe(1);

    // Capture the combobox now — changing language re-translates its own
    // accessible name ("Language" -> "Idioma"), so re-querying by that name
    // after the switch would break for the right reason (i18n really does
    // switch the whole page); keep the element reference instead.
    const languageCombobox = screen.getByRole('combobox', { name: /Language/ });
    fireEvent.click(languageCombobox);
    fireEvent.click(await screen.findByRole('option', { name: 'Español' }));

    // Let any re-fetch triggered by the language change actually settle —
    // a plain waitFor would pass on its first (pre-re-fetch) check and miss
    // a re-fire that only lands a tick later (this is what let the original
    // bug through undetected the first time this test was written).
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 300));
    });

    // The load effect must not have re-fired: still exactly one /auth/me/ call.
    expect(apiFetch.mock.calls.filter(([url]) => url === '/api/v1/auth/me/').length).toBe(1);
    // The unsaved name edit survives the language change.
    expect(screen.getByDisplayValue('Edited name')).toBeInTheDocument();
    expect(languageCombobox).toHaveTextContent('Español');
  });

  test('a successful save invalidates the shared /auth/me/ cache (useCapabilities)', async () => {
    // `useCollectionLanguage`'s `loadUserLanguage` shares a module-scoped
    // cache with `loadCapabilities`, keyed by account — but this page changes
    // `language` through its own, separate `/auth/me/` fetch and never reads
    // or writes that cache directly. Without invalidating it here, a member
    // who had already opened a collection this session (caching their
    // pre-edit language) would see the stale value again on their very next
    // visit to any collection, self-healing only on a full reload (found in
    // review, 2026-09-15). Spying on the real export, not its effect, so a
    // regression that calls something *like* invalidation but not the shared
    // one still fails this test.
    const spy = vi.spyOn(capabilities, 'invalidateMe');
    renderPage();
    await screen.findByDisplayValue('Original name');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    spy.mockRestore();
  });
});

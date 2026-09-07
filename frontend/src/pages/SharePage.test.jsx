import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import SharePage from './SharePage';

const TOKEN = 'aB3xK_9-pQrS2tUvWx1y';

function renderShare() {
  return render(
    <MemoryRouter initialEntries={[`/share/${TOKEN}`]}>
      <Routes>
        <Route path="/share/:token" element={<SharePage />} />
      </Routes>
    </MemoryRouter>
  );
}

function preview(body, ok = true) {
  return Promise.resolve({ ok, status: ok ? 200 : 404, json: () => Promise.resolve(body) });
}

beforeEach(() => {
  apiFetch.mockReset();
  document.title = '';
});
afterEach(() => vi.restoreAllMocks());

describe('SharePage — naming the collection a /share link opens (S10)', () => {
  test('asks the preview endpoint for this token on mount', async () => {
    apiFetch.mockReturnValue(preview({ headline: 'The Tool Library', description: '' }));
    renderShare();
    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith(`/api/v1/share/${TOKEN}/preview/`));
  });

  test('once it lands, the page says "Join <collection>", not "Join us on OIUEEI"', async () => {
    apiFetch.mockReturnValue(
      preview({ headline: 'The Tool Library', description: 'Borrow tools, do not buy them.' })
    );
    renderShare();

    expect(
      await screen.findByRole('heading', { name: 'Join The Tool Library', level: 1 })
    ).toBeInTheDocument();
    // The collection's own words are shown too.
    expect(screen.getByText('Borrow tools, do not buy them.')).toBeInTheDocument();
    // The generic hero title is gone.
    expect(screen.queryByRole('heading', { name: 'Join us on OIUEEI' })).toBeNull();
    await waitFor(() => expect(document.title).toBe('Join The Tool Library — OIUEEI'));
  });

  test('a localized headline is resolved to the reader’s language', async () => {
    // en.json is the test locale, so the `en` value is the one that should show.
    apiFetch.mockReturnValue(
      preview({
        headline: '{"es": "El Chalmercadillo", "ca": "El mercadet", "en": "The Swap"}',
        description: '',
      })
    );
    renderShare();

    expect(
      await screen.findByRole('heading', { name: 'Join The Swap', level: 1 })
    ).toBeInTheDocument();
  });

  test('an unknown or revoked token (404) falls back to the generic copy, no error', async () => {
    apiFetch.mockReturnValue(preview({ detail: 'Not found' }, false));
    renderShare();

    expect(
      await screen.findByRole('heading', { name: 'Join us on OIUEEI', level: 1 })
    ).toBeInTheDocument();
    // Never a visible error on this page — the join form still works.
    expect(screen.queryByText(/not found/i)).toBeNull();
    expect(screen.getByLabelText(/Email/)).toBeInTheDocument();
  });

  test('a network failure also falls back silently', async () => {
    apiFetch.mockRejectedValue(new TypeError('Failed to fetch'));
    renderShare();

    expect(
      await screen.findByRole('heading', { name: 'Join us on OIUEEI', level: 1 })
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Email/)).toBeInTheDocument();
  });

  test('a preview response missing a headline is treated as no preview', async () => {
    apiFetch.mockReturnValue(preview({ description: 'orphan description' }));
    renderShare();

    expect(
      await screen.findByRole('heading', { name: 'Join us on OIUEEI', level: 1 })
    ).toBeInTheDocument();
    expect(screen.queryByText('orphan description')).toBeNull();
  });
});

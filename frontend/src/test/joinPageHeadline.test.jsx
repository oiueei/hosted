import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: () => 'tok',
}));

import { apiFetch } from '../services/api';
import JoinPage from '../pages/JoinPage';

// JoinPage is where an anonymous visitor is asked for their email — the first
// screen of the viral funnel. It used to take the collection's name only from
// navigation state, which just one caller passes (ThingLinkbox). The hero's own
// "Join to take part" link, a refresh and a shared /join URL all arrived with
// nothing, so the page asked a stranger to join "Collection".
function renderJoin(state, search = '') {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/collections/PUB001/join', search, state }]}>
      <Routes>
        <Route path="/collections/:code/join" element={<JoinPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('JoinPage — the collection is named', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });
  afterEach(() => vi.restoreAllMocks());

  test('names the collection when arriving cold, with no navigation state', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ code: 'PUB001', headline: 'Tool Library' }),
    });

    renderJoin(undefined);

    // The named variant of the body copy — the sentence that asks for the email.
    expect(await screen.findByText(/things to Tool Library/)).toBeInTheDocument();
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/collections/PUB001/', expect.anything());
  });

  test('resolves a headline written once per language into the reader own language', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          code: 'PUB001',
          headline: JSON.stringify({ en: 'Tool Library', es: 'Biblioteca de herramientas' }),
        }),
    });

    renderJoin(undefined);

    // The test i18n runs in English, so the raw map must never reach the screen.
    expect(await screen.findByText(/things to Tool Library/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\{"en"/);
  });

  test('a collection it cannot read leaves the generic copy, not a broken name', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 404 });

    renderJoin(undefined);

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expect(screen.getByText(/Sign in to reserve/)).toBeInTheDocument();
  });

  test('a ?thing= from a "Reserve" click rides into the join request (S13)', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ code: 'PUB001', headline: 'Tool Library' }),
    });
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ message: 'sent' }),
    });

    renderJoin(undefined, '?thing=THG001');

    fireEvent.change(await screen.findByLabelText(/Email/), {
      target: { value: 'visitor@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send me a magic link' }));

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    const body = JSON.parse(globalThis.fetch.mock.calls[0][1].body);
    expect(body.collection_code).toBe('PUB001');
    expect(body.thing_code).toBe('THG001');
  });

  test('no ?thing= means no thing_code in the request', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ code: 'PUB001', headline: 'Tool Library' }),
    });
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ message: 'sent' }),
    });

    renderJoin(undefined);

    fireEvent.change(await screen.findByLabelText(/Email/), {
      target: { value: 'visitor@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send me a magic link' }));

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    const body = JSON.parse(globalThis.fetch.mock.calls[0][1].body);
    expect(body).not.toHaveProperty('thing_code');
  });
});

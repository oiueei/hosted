import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
  ),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import CollectionPage from '../pages/CollectionPage';

const LOCALIZED_TAG = '{"es": "Crianza", "ca": "Criança"}';

const COLLECTION = {
  code: 'COL001',
  headline: 'Toy library',
  description: 'Shared toys',
  status: 'ACTIVE',
  visibility: 'PRIVATE',
  mode: 'COMMUNITY',
  owner: 'ABC123',
  owner_name: 'Test User',
  thumbnail_url: '',
  tags: [LOCALIZED_TAG, 'Books'],
  things: [
    {
      code: 'THG001',
      headline: 'Cot',
      type: 'GIFT_THING',
      status: 'ACTIVE',
      tags: [LOCALIZED_TAG],
      owner: 'ABC123',
    },
    {
      code: 'THG002',
      headline: 'Picture book',
      type: 'GIFT_THING',
      status: 'ACTIVE',
      tags: ['Books'],
      owner: 'ABC123',
    },
  ],
  invites: [],
  is_paused: false,
  allowed_thing_types: [],
};

function setApi() {
  apiFetch.mockImplementation(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(COLLECTION) })
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ABC123');
  vi.clearAllMocks();
  setApi();
});

describe('CollectionPage tag filter chips (S6)', () => {
  test('resolves a localized tag label instead of rendering raw JSON, and still filters by it', async () => {
    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    const chip = await screen.findByRole('button', { name: /Crianza \(1\)/ });
    // The resolved label never leaks the raw braces.
    expect(screen.queryByText(/\{"es"/)).not.toBeInTheDocument();

    fireEvent.click(chip);

    await waitFor(() => {
      expect(screen.getByText('Cot')).toBeInTheDocument();
      expect(screen.queryByText('Picture book')).not.toBeInTheDocument();
    });
  });
});

/**
 * The render cap (DESIGN §7).
 *
 * The collection serialises every thing it holds with no ceiling, so a big
 * lending library mounted one ThingLinkbox — theeeme, localisation and booking
 * view-model each — per item on first paint. The cap is on rendering, not on
 * the payload, because the tag chips count across the whole collection and a
 * paginated payload would make those counts lie.
 */
describe('CollectionPage card cap', () => {
  // 27 = the 24-card cap plus three, which is all the cap needs to be
  // observable. Each card mounts a real ThingLinkbox (theeeme, localisation,
  // booking view-model), so the fixture is deliberately no bigger than the
  // claim — under coverage instrumentation a larger one times out.
  const many = Array.from({ length: 27 }, (_, i) => ({
    code: `THG${String(i).padStart(3, '0')}`,
    headline: `Thing ${i}`,
    type: 'GIFT_THING',
    status: 'ACTIVE',
    tags: i < 5 ? ['Books'] : [],
    owner: 'ABC123',
    created: `2026-08-${String((i % 28) + 1).padStart(2, '0')}T10:00:00Z`,
  }));

  const renderBig = () => {
    apiFetch.mockImplementation(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ ...COLLECTION, tags: ['Books'], things: many }),
      })
    );
    return render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );
  };

  const cards = () => screen.getAllByRole('link', { name: /^Thing \d+$/ });

  test('a big collection paints 24 cards and offers the rest', { timeout: 40000 }, async () => {
    renderBig();

    await screen.findByRole('button', { name: /show 3 more things/i });
    expect(cards()).toHaveLength(24);
  });

  test(
    'Show more appends the rest without reshuffling what was already there',
    { timeout: 40000 },
    async () => {
      renderBig();

      await screen.findByRole('button', { name: /show 3 more things/i });
      const first = cards()[0].textContent;
      fireEvent.click(screen.getByRole('button', { name: /show 3 more things/i }));

      // Wait on one cheap text query rather than re-running a 30-node role query.
      await screen.findByText('Thing 0');
      expect(cards()).toHaveLength(27);
      expect(cards()[0].textContent).toBe(first);
      expect(screen.queryByRole('button', { name: /more things/i })).not.toBeInTheDocument();
    }
  );

  test('the tag chips count the whole collection, not just the painted cards', async () => {
    renderBig();

    // 30 things, 5 of them tagged — both counts are over the cap's head.
    expect(await screen.findByRole('button', { name: /All \(27\)/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Books \(5\)/ })).toBeInTheDocument();
  });

  test('picking a tag starts the count again, so a small result needs no button', async () => {
    renderBig();

    fireEvent.click(await screen.findByRole('button', { name: /Books \(5\)/ }));

    await waitFor(() => expect(cards()).toHaveLength(5));
    expect(screen.queryByRole('button', { name: /more things/i })).not.toBeInTheDocument();
  });
});

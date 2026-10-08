import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

// The real card is `memo(ThingLinkbox)`: it paints again only when a prop changes.
// This stand-in keeps that, and counts its paints per thing. A callback the page
// rebuilds on every render (`reloadCollection` was one) is a prop that always
// changes, so every card painted again for every state change of the page — up
// to 24 of them per key typed in the broadcast box.
const painted = vi.hoisted(() => vi.fn());
vi.mock('../components/ThingLinkbox', async () => {
  const { memo } = await vi.importActual('react');
  return {
    default: memo(function CountingCard({ thing }) {
      painted(thing.code);
      return <div>{thing.headline}</div>;
    }),
  };
});

import { apiFetch } from '../services/api';
import CollectionPage from '../pages/CollectionPage';

const COLLECTION = {
  code: 'COL001',
  headline: 'Toy library',
  description: '',
  status: 'ACTIVE',
  visibility: 'PRIVATE',
  mode: 'COMMUNITY',
  owner: 'ABC123',
  owner_name: 'Lala',
  is_curator: true,
  tags: ['Toys', 'Books'],
  things: [
    { code: 'THG001', headline: 'Cot', type: 'GIFT_THING', status: 'ACTIVE', tags: ['Toys'] },
    {
      code: 'THG002',
      headline: 'Picture book',
      type: 'GIFT_THING',
      status: 'ACTIVE',
      tags: ['Books'],
    },
  ],
  invites: [],
  co_owners: [],
  is_paused: false,
  allowed_thing_types: [],
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ABC123');
  vi.clearAllMocks();
  apiFetch.mockImplementation(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(COLLECTION) })
  );
});

describe('CollectionPage cards', () => {
  test('a card still on screen is not painted again when the page changes around it', async () => {
    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );
    const chip = await screen.findByRole('button', { name: 'Toys (1)' });
    const paintsOf = (code) => painted.mock.calls.filter(([c]) => c === code).length;
    await waitFor(() => expect(paintsOf('THG001')).toBeGreaterThan(0));
    const before = paintsOf('THG001');

    // Picking a tag re-renders the page; the "Cot" card stays, with the same thing.
    fireEvent.click(chip);
    await waitFor(() => expect(screen.queryByText('Picture book')).toBeNull());

    expect(screen.getByText('Cot')).toBeInTheDocument();
    expect(paintsOf('THG001')).toBe(before);
  });
});

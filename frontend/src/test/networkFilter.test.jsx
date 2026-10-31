import { render, screen, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));
vi.mock('../deployment', async (orig) => ({ ...(await orig()), curatorGuidePath: null }));

import { apiFetch } from '../services/api';
import CollectionPage from '../pages/CollectionPage';
import declarePalette from './declarePalette';

/**
 * A network's page filters by who lends: a second row of chips next to the tags, one
 * per dinamizador with something to show, named by their pickup point. The choice is in
 * the address (`/library/:code/:curatorCode`), so it can be shared; the tags and the
 * dinamizador narrow the same list together. Anything else in that place is the
 * collection as it is.
 */
const NAMES = { FOUN01: 'Lala', ENTA01: 'Lele', ENTB01: 'Lili', ENTC01: 'Lulu' };
const thing = (code, owner, headline, extra = {}) => ({
  code,
  type: 'LEND_THING',
  owner,
  owner_name: NAMES[owner],
  headline,
  description: '',
  status: 'ACTIVE',
  fee: null,
  availability: '',
  location: '',
  condition: '',
  thumbnail_url: '',
  gallery: [],
  gallery_urls: [],
  available_today: true,
  next_available: null,
  tags: [],
  pending_questions: 0,
  my_pending_booking: null,
  pending_booking: null,
  bookings: [],
  created: '2026-09-01T10:00:00Z',
  network_point: { display_name: NAMES[owner], address: '', hours_note: '', contact: '' },
  ...extra,
});

const NETWORK = {
  code: 'COL001',
  headline: 'Neighbourhood network',
  description: '',
  status: 'ACTIVE',
  visibility: 'PRIVATE',
  kind: 'LIBRARY',
  mode: 'NETWORK',
  owner: 'FOUN01',
  owner_name: 'Lala',
  is_curator: false,
  is_member: true,
  co_owners: [
    { code: 'ENTA01', name: 'Lele' },
    { code: 'ENTB01', name: 'Lili' },
    { code: 'ENTC01', name: 'Lulu' },
  ],
  tags: ['Garden', 'Kitchen'],
  invites: [],
  is_paused: false,
  allowed_thing_types: ['LEND_THING', 'RENT_THING'],
  things: [
    thing('THG001', 'ENTA01', 'Drill', {
      tags: ['Garden'],
      network_point: { display_name: 'Cooperativa La Fusteria', address: '', hours_note: '' },
    }),
    thing('THG002', 'ENTA01', 'Saw', { tags: ['Kitchen'] }),
    thing('THG003', 'ENTB01', 'Rake', { tags: ['Garden'] }),
    thing('THG004', 'FOUN01', 'Ladder'),
    // A dinamizador whose only thing is hidden shows no chip.
    thing('THG005', 'ENTC01', 'Hidden thing', { status: 'INACTIVE' }),
  ],
};

function Where() {
  const { pathname } = useLocation();
  return <div data-testid="where">{pathname}</div>;
}

function renderAt(path, collection = NETWORK) {
  apiFetch.mockImplementation((url) =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(url.includes('/inbox/') ? [] : collection),
    })
  );
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Where />
      <Routes>
        <Route path="/:kind/:code/:curatorCode?" element={<CollectionPage />} />
      </Routes>
    </MemoryRouter>
  );
}

const grid = () => document.querySelector('.things-grid');
const shown = () =>
  within(grid())
    .getAllByRole('heading', { level: 3 })
    .map((h) => h.textContent);
const lenderRow = () => screen.getByRole('group', { name: 'Who lends' });
const chip = (name) => within(lenderRow()).getByRole('button', { name: new RegExp(`^${name}`) });

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'MEMB01');
  declarePalette({
    color_01: 'bus',
    color_02: 'suomenlinna-light',
    color_03: 'copper',
    color_04: 'black',
    color_05: 'white',
    color_06: 'white',
  });
  vi.clearAllMocks();
});

describe('the network’s filter by who lends', () => {
  test('one chip per dinamizador with something to show, by the name of their point', async () => {
    renderAt('/library/COL001');

    await screen.findByText('Drill');
    const names = within(lenderRow())
      .getAllByRole('button')
      .map((b) => b.textContent);
    expect(names).toEqual(['All (4)', 'Cooperativa La Fusteria (2)', 'Lala (1)', 'Lili (1)']);
    expect(within(lenderRow()).queryByText(/Lulu|Hidden/)).toBeNull();
  });

  test('pressing one filters the cards and puts the dinamizador in the address', async () => {
    renderAt('/library/COL001');
    await screen.findByText('Drill');

    fireEvent.click(chip('Cooperativa'));

    expect(screen.getByTestId('where')).toHaveTextContent('/library/COL001/ENTA01');
    expect(shown()).toEqual(expect.arrayContaining(['Drill', 'Saw']));
    expect(shown()).toHaveLength(2);
    expect(chip('Cooperativa')).toHaveAttribute('aria-pressed', 'true');
    expect(chip('All')).toHaveAttribute('aria-pressed', 'false');
  });

  test('"All" goes back to the collection’s own address', async () => {
    renderAt('/library/COL001/ENTA01');
    await screen.findByText('Drill');

    fireEvent.click(chip('All'));

    expect(screen.getByTestId('where')).toHaveTextContent(/^\/library\/COL001$/);
    expect(shown()).toHaveLength(4);
  });

  test('an address naming a dinamizador opens already filtered', async () => {
    renderAt('/library/COL001/ENTB01');

    await screen.findByText('Rake');
    expect(shown()).toEqual(['Rake']);
    expect(chip('Lili')).toHaveAttribute('aria-pressed', 'true');
  });

  test('the dinamizador and a tag narrow the list together', async () => {
    renderAt('/library/COL001/ENTA01');
    await screen.findByText('Drill');

    fireEvent.click(screen.getByRole('button', { name: /^Garden/ }));

    expect(shown()).toEqual(['Drill']);
  });

  test('with a single dinamizador there is no row: it would be the same button twice', async () => {
    const onlyLele = {
      ...NETWORK,
      things: NETWORK.things.filter((t) => t.owner === 'ENTA01'),
    };
    renderAt('/library/COL001', onlyLele);

    await screen.findByText('Drill');
    expect(screen.queryByRole('group', { name: 'Who lends' })).toBeNull();
    expect(shown()).toHaveLength(2);
  });

  test('an address filtered by the only one there is still shows all their things, with no error', async () => {
    const onlyLele = {
      ...NETWORK,
      things: NETWORK.things.filter((t) => t.owner === 'ENTA01'),
    };
    renderAt('/library/COL001/ENTA01', onlyLele);

    await screen.findByText('Drill');
    expect(shown()).toHaveLength(2);
    expect(screen.queryByText(/not found|error/i)).toBeNull();
  });

  test('with two it appears', async () => {
    const two = {
      ...NETWORK,
      things: NETWORK.things.filter((t) => t.owner !== 'ENTB01' && t.owner !== 'FOUN01'),
    };
    renderAt('/library/COL001', {
      ...two,
      things: [...two.things, NETWORK.things.find((t) => t.owner === 'ENTB01')],
    });

    await screen.findByText('Drill');
    expect(lenderRow()).toBeInTheDocument();
  });

  test('a code that is nobody’s shows the whole collection, with no error', async () => {
    renderAt('/library/COL001/NOBODY');

    await screen.findByText('Drill');
    expect(shown()).toHaveLength(4);
    expect(chip('All')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByText(/not found|error/i)).toBeNull();
  });

  test('a dinamizador with nothing to show is not a filter either', async () => {
    renderAt('/library/COL001/ENTC01');

    await screen.findByText('Drill');
    expect(shown()).toHaveLength(4);
  });

  test('moving between filters does not load the collection again', async () => {
    renderAt('/library/COL001');
    await screen.findByText('Drill');
    const loads = () => apiFetch.mock.calls.filter(([u]) => u === '/api/v1/collections/COL001/');
    const before = loads().length;

    fireEvent.click(chip('Lili'));
    fireEvent.click(chip('All'));

    expect(loads()).toHaveLength(before);
  });

  test('a collection that is not a network has no such row, and an address naming a code shows it as it is', async () => {
    renderAt('/library/COL001/ENTA01', { ...NETWORK, mode: 'PROPRIETARY' });

    await screen.findByText('Drill');
    expect(screen.queryByRole('group', { name: 'Who lends' })).toBeNull();
    expect(shown()).toHaveLength(4);
  });
});

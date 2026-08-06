import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

const navigate = vi.fn();
vi.mock('react-router-dom', async () => ({
  ...(await vi.importActual('react-router-dom')),
  useNavigate: () => navigate,
}));

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: () => 'tok',
  extractApiError: () => null,
}));

import { apiFetch } from '../services/api';
import DeleteThingPage from '../pages/DeleteThingPage';
import DeleteCollectionPage from '../pages/DeleteCollectionPage';
import RemoveGuestPage from '../pages/RemoveGuestPage';
import LeaveCollectionPage from '../pages/LeaveCollectionPage';

// The four confirms that end something for good. Until this release they were
// pixel-identical to "Save" — same theeeme primary button, no icon, and in two
// cases a single line of warning that didn't name what actually goes.
//
// The reason these need tests at all is in this very release: `1f2d421` revived
// a transfer confirm that had NEVER rendered. Nothing broke when it went
// missing, nothing went red, and the guard was simply absent for months. A
// confirm is exactly the kind of thing that fails silently, because its failure
// mode is "the destructive action just happens".
//
// So each page is held to three claims: the destructive action does not fire
// until the confirm is pressed; the button carries the danger affordance; and
// Cancel goes back without touching anything.

const COLLECTION = { code: 'COL001', headline: 'Kitchen Collection', owner: 'USR001' };
const THING = { code: 'THG001', headline: 'Blue armchair', owner: 'USR001' };

function mockApi({ ok = true } = {}, body = {}) {
  apiFetch.mockImplementation((url, opts) => {
    if (opts?.method) {
      return Promise.resolve({ ok, status: ok ? 200 : 400, json: async () => ({}) });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => body });
  });
}

/** Every call that would change something server-side. */
const mutations = () =>
  apiFetch.mock.calls.filter(([, o]) => o?.method).map(([u, o]) => `${o.method} ${u}`);

/** The icon HDS renders inside the button, the affordance the release added. */
const iconInside = (name) =>
  screen.getByRole('button', { name }).querySelector('svg, [class*="hds-icon"]');

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'USR001');
  vi.clearAllMocks();
});
afterEach(() => vi.restoreAllMocks());

describe('DeleteThingPage', () => {
  const renderPage = () =>
    render(
      <MemoryRouter initialEntries={['/things/THG001/delete']}>
        <Routes>
          <Route path="/things/:thingCode/delete" element={<DeleteThingPage />} />
        </Routes>
      </MemoryRouter>
    );

  test('names what goes that is not the owner’s, and deletes nothing on arrival', async () => {
    mockApi({}, THING);
    renderPage();
    await screen.findByText(/cannot be undone/);

    // "This action cannot be undone" said none of this: the questions are other
    // people's, the journey is the item's history, and somebody may be waiting
    // on a hold that dies here.
    expect(screen.getByText(/Every question other people asked about it/i)).toBeInTheDocument();
    expect(screen.getByText(/pending request on it/i)).toBeInTheDocument();
    expect(mutations()).toEqual([]);
  });

  test('the confirm carries the danger affordance, not a Save-shaped button', async () => {
    mockApi({}, THING);
    renderPage();
    await screen.findByText(/cannot be undone/);

    expect(iconInside('Delete')).toBeTruthy();
  });

  test('deleting fires exactly one DELETE and leaves the page', async () => {
    mockApi({}, THING);
    renderPage();
    await screen.findByText(/cannot be undone/);

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(mutations()).toEqual(['DELETE /api/v1/things/THG001/']));
    expect(navigate).toHaveBeenCalled();
  });

  test('cancelling destroys nothing', async () => {
    mockApi({}, THING);
    renderPage();
    await screen.findByText(/cannot be undone/);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(mutations()).toEqual([]);
    expect(navigate).toHaveBeenCalled();
  });

  test('a refused delete keeps the page and says so', async () => {
    mockApi({ ok: false }, THING);
    renderPage();
    await screen.findByText(/cannot be undone/);
    navigate.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    expect(await screen.findByText(/Error deleting thing/i)).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
  });
});

describe('DeleteCollectionPage', () => {
  const renderPage = () =>
    render(
      <MemoryRouter initialEntries={['/collections/COL001/delete']}>
        <Routes>
          <Route path="/collections/:code/delete" element={<DeleteCollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

  test('says the members’ things go too, and that there is no way back', async () => {
    mockApi({}, COLLECTION);
    renderPage();
    await screen.findByText(/cannot be undone/);

    // The owner is the only person who can do this and the only one warned, so
    // the warning has to name what leaves that isn't theirs.
    expect(screen.getByText(/your members added/i)).toBeInTheDocument();
    expect(screen.getByText(/save it before you press delete/i)).toBeInTheDocument();
    // And the one thing that survives, so the copy isn't scarier than the truth.
    expect(screen.getByText(/belongs to another collection stays there/i)).toBeInTheDocument();
    expect(mutations()).toEqual([]);
  });

  test('the confirm carries the danger affordance', async () => {
    mockApi({}, COLLECTION);
    renderPage();
    await screen.findByText(/cannot be undone/);

    expect(iconInside('Delete')).toBeTruthy();
  });

  test('deleting fires one DELETE and goes home', async () => {
    mockApi({}, COLLECTION);
    renderPage();
    await screen.findByText(/cannot be undone/);

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(mutations()).toEqual(['DELETE /api/v1/collections/COL001/']));
    expect(navigate).toHaveBeenCalledWith('/');
  });

  test('cancelling destroys nothing', async () => {
    mockApi({}, COLLECTION);
    renderPage();
    await screen.findByText(/cannot be undone/);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(mutations()).toEqual([]);
  });
});

describe('RemoveGuestPage', () => {
  const renderPage = () =>
    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/collections/COL001/invites/remove',
            state: { guestCode: 'GST001', guestName: 'Lele', backLabel: 'Guests' },
          },
        ]}
      >
        <Routes>
          <Route path="/collections/:code/invites/remove" element={<RemoveGuestPage />} />
        </Routes>
      </MemoryRouter>
    );

  test('names the guest and warns before anything happens', async () => {
    mockApi({}, COLLECTION);
    renderPage();

    expect(await screen.findByText(/lose access immediately/i)).toBeInTheDocument();
    expect(mutations()).toEqual([]);
  });

  test('the confirm carries the danger affordance', async () => {
    mockApi({}, COLLECTION);
    renderPage();
    await screen.findByText(/lose access immediately/i);

    expect(iconInside('Remove')).toBeTruthy();
  });

  test('removing sends the guest code, once', async () => {
    mockApi({}, COLLECTION);
    renderPage();
    await screen.findByText(/lose access immediately/i);

    fireEvent.click(screen.getByRole('button', { name: 'Remove' }));

    await waitFor(() => expect(mutations()).toEqual(['DELETE /api/v1/collections/COL001/invite/']));
    const [, options] = apiFetch.mock.calls.find(([, o]) => o?.method === 'DELETE');
    expect(JSON.parse(options.body)).toEqual({ user_code: 'GST001' });
  });

  test('cancelling removes nobody', async () => {
    mockApi({}, COLLECTION);
    renderPage();
    await screen.findByText(/lose access immediately/i);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(mutations()).toEqual([]);
  });
});

describe('LeaveCollectionPage', () => {
  const renderPage = () =>
    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/collections/COL001/leave',
            state: { headline: 'Kitchen Collection' },
          },
        ]}
      >
        <Routes>
          <Route path="/collections/:code/leave" element={<LeaveCollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

  test('warns that leaving a private group needs a fresh invitation to undo', async () => {
    mockApi({}, COLLECTION);
    renderPage();

    expect(await screen.findByText(/unless the owner invites you again/i)).toBeInTheDocument();
    expect(mutations()).toEqual([]);
  });

  test('the confirm carries the danger affordance', async () => {
    mockApi({}, COLLECTION);
    renderPage();
    await screen.findByText(/unless the owner invites you again/i);

    expect(iconInside('Leave the group')).toBeTruthy();
  });

  test('leaving posts once and goes home — the collection may now be unreadable', async () => {
    mockApi({}, COLLECTION);
    renderPage();
    await screen.findByText(/unless the owner invites you again/i);

    fireEvent.click(screen.getByRole('button', { name: 'Leave the group' }));

    await waitFor(() => expect(mutations()).toEqual(['POST /api/v1/collections/COL001/leave/']));
    expect(navigate).toHaveBeenCalledWith('/');
  });

  test('cancelling keeps the membership', async () => {
    mockApi({}, COLLECTION);
    renderPage();
    await screen.findByText(/unless the owner invites you again/i);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(mutations()).toEqual([]);
  });
});

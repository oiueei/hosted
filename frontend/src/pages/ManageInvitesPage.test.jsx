import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { describe, test, expect, vi, afterEach, beforeEach } from 'vitest';
import ManageInvitesPage from './ManageInvitesPage';

// The same JSON shape CollectionSerializer emits (subset the page reads).
const COLLECTION = {
  code: 'COL001',
  headline: 'Book Club',
  owner: 'OWNER1',
  invites: [{ code: 'GST001', email: 'ana@example.com', name: 'Ana' }],
  pending_invites: [{ code: 'RSVP01', email: 'pending@example.com' }],
};

// A member's suggestion, as `CollectionSerializer.pending_proposals` emits it.
const PROPOSAL = {
  code: 'PRP001',
  email: 'lili@example.com',
  note: 'my downstairs neighbour',
  proposer_name: 'Lele',
};

function mockRoutes({
  collection = COLLECTION,
  invite = { status: 200 },
  proposal = { status: 200 },
} = {}) {
  // An answered suggestion stops being pending server-side, so the reload an
  // approval triggers must not hand the same card straight back. Modelling that
  // is what makes "it disappears" a claim about the page and not about the mock.
  let answered = false;
  globalThis.fetch = vi.fn((url) => {
    const respond = (status, body) =>
      Promise.resolve({ ok: status < 400, status, json: async () => body });
    if (url.endsWith('/invite/')) {
      return respond(invite.status, invite.body ?? { message: 'Invitation sent' });
    }
    if (url.includes('/proposals/')) {
      if (proposal.status < 400) answered = true;
      return respond(proposal.status, proposal.body ?? { message: 'Invitation sent' });
    }
    return respond(200, answered ? { ...collection, pending_proposals: [] } : collection);
  });
}

const proposalCalls = () => globalThis.fetch.mock.calls.filter(([u]) => u.includes('/proposals/'));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/collections/COL001/invites']}>
      <Routes>
        <Route path="/collections/:code/invites" element={<ManageInvitesPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('ManageInvitesPage (the guest list)', () => {
  beforeEach(() => {
    localStorage.setItem('userCode', 'OWNER1');
  });
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  test('the owner invites by email: POST contract, optimistic pending row, cleared input', async () => {
    mockRoutes();
    renderPage();
    await screen.findByText(/Ana/);

    fireEvent.change(screen.getByLabelText('Guest email'), {
      target: { value: 'new@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Invite' }));

    await screen.findByText('Invitation sent.');
    const [url, options] = globalThis.fetch.mock.calls.find(([u]) => u.endsWith('/invite/'));
    expect(url).toBe('/api/v1/collections/COL001/invite/');
    expect(options.method).toBe('POST');
    expect(JSON.parse(options.body)).toEqual({ email: 'new@example.com' });
    // The new address appears as Pending without waiting for a refetch.
    expect(screen.getByText('new@example.com')).toBeInTheDocument();
    expect(screen.getByLabelText('Guest email')).toHaveValue('');
  });

  test('the guest table carries a name', async () => {
    renderPage();

    expect(
      await screen.findByRole('table', { name: 'Guests of this collection' })
    ).toBeInTheDocument();
  });

  test('a rejected invite surfaces the backend detail, not a generic error', async () => {
    mockRoutes({ invite: { status: 400, body: { error: 'User is already a member' } } });
    renderPage();
    await screen.findByText(/Ana/);

    fireEvent.change(screen.getByLabelText('Guest email'), {
      target: { value: 'ana@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Invite' }));

    expect(await screen.findByText('User is already a member')).toBeInTheDocument();
  });

  test('resend fires the invite POST for that pending guest', async () => {
    mockRoutes();
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Resend invitation to this guest' }));

    await screen.findByText('Invitation resent.');
    const [, options] = globalThis.fetch.mock.calls.find(([u]) => u.endsWith('/invite/'));
    expect(JSON.parse(options.body)).toEqual({ email: 'pending@example.com' });
  });

  // ── Members' recommendations ──────────────────────────────────────────────
  //
  // A member suggests somebody and the owner decides. The guarantee running
  // through all of these: until the owner says yes, the person named has not
  // been contacted and does not know they were suggested — so the page must
  // never read as though an invitation already went out.

  test('a suggestion shows who was recommended, by whom, and their note', async () => {
    mockRoutes({ collection: { ...COLLECTION, pending_proposals: [PROPOSAL] } });
    renderPage();

    expect(await screen.findByText('lili@example.com')).toBeInTheDocument();
    expect(screen.getByText(/recommended by Lele/)).toBeInTheDocument();
    // The note is the proposer's word FOR THE OWNER — it is the whole reason
    // this is a decision rather than a guess at an unfamiliar address.
    expect(screen.getByText(/my downstairs neighbour/)).toBeInTheDocument();
    expect(screen.getByText(/Nobody has been contacted/)).toBeInTheDocument();
  });

  test('approving posts to the proposal and clears it from the list', async () => {
    mockRoutes({ collection: { ...COLLECTION, pending_proposals: [PROPOSAL] } });
    renderPage();
    await screen.findByText('lili@example.com');

    fireEvent.click(screen.getByRole('button', { name: 'Invite them' }));

    await waitFor(() => expect(proposalCalls()).toHaveLength(1));
    const [url, options] = proposalCalls()[0];
    expect(url).toBe('/api/v1/proposals/PRP001/approve/');
    expect(options.method).toBe('POST');
    // Answered means answered: an owner must not be asked the same question
    // twice, nor be able to approve it twice from a stale card.
    await waitFor(() => expect(screen.queryByText('lili@example.com')).toBeNull());
  });

  test('declining goes to the reject endpoint, never to approve', async () => {
    mockRoutes({ collection: { ...COLLECTION, pending_proposals: [PROPOSAL] } });
    renderPage();
    await screen.findByText('lili@example.com');

    fireEvent.click(screen.getByRole('button', { name: 'Not this time' }));

    await waitFor(() => expect(proposalCalls()).toHaveLength(1));
    expect(proposalCalls()[0][0]).toBe('/api/v1/proposals/PRP001/reject/');
    await waitFor(() => expect(screen.queryByText('lili@example.com')).toBeNull());
  });

  test('a refused decision keeps the suggestion and surfaces the reason', async () => {
    mockRoutes({
      collection: { ...COLLECTION, pending_proposals: [PROPOSAL] },
      proposal: {
        status: 429,
        body: { error: 'Daily invitation limit reached. Try again tomorrow.' },
      },
    });
    renderPage();
    await screen.findByText('lili@example.com');

    fireEvent.click(screen.getByRole('button', { name: 'Invite them' }));

    // The backend's own words: "not now" and "no" call for different replies
    // from the owner, and a generic error would hide which one this was.
    expect(await screen.findByText(/Daily invitation limit reached/)).toBeInTheDocument();
    // The card stays, so the owner can answer tomorrow.
    expect(screen.getByText('lili@example.com')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Invite them' })).toBeInTheDocument();
  });

  test('a member never sees suggestions meant for the owner', async () => {
    localStorage.setItem('userCode', 'GUEST9');
    mockRoutes({ collection: { ...COLLECTION, pending_proposals: [PROPOSAL] } });
    renderPage();
    await screen.findByText(/Ana/);

    // The note is one member's private word about a third person, written for
    // the owner alone; the address is somebody who has not agreed to be here.
    expect(screen.queryByText('lili@example.com')).toBeNull();
    expect(screen.queryByText(/my downstairs neighbour/)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Invite them' })).toBeNull();
  });

  test('with nothing suggested the section stays out of the way', async () => {
    mockRoutes({ collection: { ...COLLECTION, pending_proposals: [] } });
    renderPage();
    await screen.findByText(/Ana/);

    expect(screen.queryByRole('heading', { name: 'Recommendations' })).toBeNull();
  });

  test('a non-owner sees the list but no invite controls', async () => {
    localStorage.setItem('userCode', 'GUEST9');
    mockRoutes();
    renderPage();
    await screen.findByText(/Ana/);

    expect(screen.queryByLabelText('Guest email')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Remove guest from this collection' })
    ).not.toBeInTheDocument();
    await waitFor(() => {
      expect(globalThis.fetch.mock.calls.some(([u]) => u.endsWith('/invite/'))).toBe(false);
    });
  });
});

/**
 * A load failure must say so, not draw a page that contradicts reality.
 *
 * This was the only data page in the app with no persistent error state: a 403
 * or a dead network raised an auto-closing toast and then rendered isOwner=false
 * over an empty list, so the owner read "no guests, and you can't invite anyone"
 * with no explanation and no way to retry.
 */
describe('ManageInvitesPage load failures', () => {
  beforeEach(() => {
    localStorage.setItem('userCode', 'OWNER1');
  });
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  const failWith = (status) => {
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: false, status, json: async () => ({}) }));
  };

  test('a server error stops the page instead of showing an empty guest list', async () => {
    failWith(500);
    renderPage();

    expect(await screen.findByText(/error loading/i)).toBeInTheDocument();
    // Crucially: it does not offer the invite form it has no right to show.
    expect(screen.queryByRole('button', { name: /^invite$/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  test('a 403 says it is a permission problem, not a generic failure', async () => {
    failWith(403);
    renderPage();

    expect(
      await screen.findByText(/do not have access to this collection's guests/i)
    ).toBeInTheDocument();
  });

  test('Retry re-fetches, and a collection that loads the second time renders normally', async () => {
    let attempt = 0;
    globalThis.fetch = vi.fn(() => {
      attempt += 1;
      return attempt === 1
        ? Promise.resolve({ ok: false, status: 500, json: async () => ({}) })
        : Promise.resolve({ ok: true, status: 200, json: async () => COLLECTION });
    });

    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: /retry/i }));

    expect(await screen.findByText(/Ana/)).toBeInTheDocument();
    expect(screen.queryByText(/error loading/i)).not.toBeInTheDocument();
  });
});

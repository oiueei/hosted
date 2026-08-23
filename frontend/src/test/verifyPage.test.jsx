import { render, screen, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router';
import { StrictMode } from 'react';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';
import VerifyPage from '../pages/VerifyPage';

// VerifyPage talks to the backend via raw `fetch` (not the apiFetch wrapper), so
// we drive both legs of the auto-commit (GET preview, POST commit) from here.
// FRONTEND B1: the `requires_confirmation → POST` auto-commit and its
// `committedRef` StrictMode guard had zero behavioural coverage — the smoke
// test mocks fetch to 400, so this path never executed.

const CODE = 'RSVPTEST123';

function mockResponse(body, ok = true, status = 200) {
  return { ok, status, json: () => Promise.resolve(body) };
}

function renderVerify(wrapInStrictMode = false) {
  const tree = (
    <MemoryRouter initialEntries={[`/verify/${CODE}`]}>
      <Routes>
        <Route path="/verify/:code" element={<VerifyPage />} />
        {/* catch-all so the login/invite/user navigations don't crash */}
        <Route path="*" element={<div data-testid="navigated" />} />
      </Routes>
    </MemoryRouter>
  );
  return render(wrapInStrictMode ? <StrictMode>{tree}</StrictMode> : tree);
}

const postCalls = (mock) => mock.mock.calls.filter(([, opts]) => opts?.method === 'POST');
const getCalls = (mock) => mock.mock.calls.filter(([, opts]) => !opts?.method);

describe('VerifyPage auto-commit', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test('commits a booking ACCEPT with a single POST when GET requires confirmation', async () => {
    globalThis.fetch = vi.fn((url, opts = {}) =>
      opts.method === 'POST'
        ? Promise.resolve(mockResponse({ action: 'BOOKING_ACCEPT' }))
        : Promise.resolve(mockResponse({ requires_confirmation: true }))
    );

    renderVerify();

    expect(await screen.findByText('The hold has been confirmed!')).toBeInTheDocument();
    expect(screen.getByText('Confirmed!')).toBeInTheDocument();

    // One preview GET + exactly one committing POST — nothing more.
    expect(getCalls(globalThis.fetch)).toHaveLength(1);
    expect(postCalls(globalThis.fetch)).toHaveLength(1);
    expect(globalThis.fetch.mock.calls[1][0]).toBe(`/api/v1/auth/verify/${CODE}/`);
  });

  test('commits a booking REJECT and shows the rejected screen', async () => {
    globalThis.fetch = vi.fn((url, opts = {}) =>
      opts.method === 'POST'
        ? Promise.resolve(mockResponse({ action: 'BOOKING_REJECT' }))
        : Promise.resolve(mockResponse({ requires_confirmation: true }))
    );

    renderVerify();

    expect(await screen.findByText('The hold has been rejected.')).toBeInTheDocument();
    expect(screen.getByText('Rejected')).toBeInTheDocument();
    expect(postCalls(globalThis.fetch)).toHaveLength(1);
  });

  test('treats an unknown commit action as an invalid/expired link', async () => {
    globalThis.fetch = vi.fn((url, opts = {}) =>
      opts.method === 'POST'
        ? Promise.resolve(mockResponse({ action: 'SOMETHING_ELSE' }))
        : Promise.resolve(mockResponse({ requires_confirmation: true }))
    );

    renderVerify();

    expect(await screen.findByText('Invalid or expired link.')).toBeInTheDocument();
    expect(postCalls(globalThis.fetch)).toHaveLength(1);
  });

  test('never commits when the GET preview is non-OK (expired link)', async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve(mockResponse({ error: 'expired' }, false, 400)));

    renderVerify();

    expect(await screen.findByText('Invalid or expired link.')).toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledTimes(1); // the GET only — no POST
    expect(postCalls(globalThis.fetch)).toHaveLength(0);
  });

  test('never commits when the GET request throws (offline)', async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('network down')));

    renderVerify();

    expect(await screen.findByText('Connection error.')).toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    expect(postCalls(globalThis.fetch)).toHaveLength(0);
  });

  test('StrictMode double-invoke fires the committing POST exactly once', async () => {
    // StrictMode (dev build) mounts → runs the effect twice. committedRef must
    // keep the irreversible booking-decision POST to a single fire even though
    // the preview GET runs twice. Method-keyed mock so the assertion is robust
    // to the async interleaving of the two effect runs.
    globalThis.fetch = vi.fn((url, opts = {}) =>
      opts.method === 'POST'
        ? Promise.resolve(mockResponse({ action: 'BOOKING_ACCEPT' }))
        : Promise.resolve(mockResponse({ requires_confirmation: true }))
    );

    renderVerify(true);

    expect(await screen.findByText('The hold has been confirmed!')).toBeInTheDocument();
    // The preview GET ran twice (proving the double-invoke actually happened,
    // so this test is not vacuous) …
    expect(getCalls(globalThis.fetch)).toHaveLength(2);
    // … but the commit POST fired exactly once.
    expect(postCalls(globalThis.fetch)).toHaveLength(1);
  });
});

/**
 * Every refusal this page can meet consumes its RSVP — the booking is already
 * decided, the suggestion is already answered — except one. An approval the
 * deployment's daily invitation cap or the group's member ceiling turns down
 * leaves the proposal pending and both links alive **on purpose**: "not now",
 * so the owner can answer tomorrow. The page showed that as "Invalid or expired
 * link", which is the one thing it is not, and the owner it was telling to stop
 * clicking had no other route back to the decision.
 *
 * `retryable` is the server's word for which of the two this is (it is not
 * inferable from the status: a full collection and a settled suggestion both
 * answer 400), so both halves are pinned here — the one that survives and the
 * one that really is over.
 */
describe('a refusal the link survives', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  const previewApprove = { requires_confirmation: true, action: 'PROPOSAL_APPROVE' };

  function mockRefusal(body, status) {
    globalThis.fetch = vi.fn((url, opts = {}) =>
      opts.method === 'POST'
        ? Promise.resolve(mockResponse(body, false, status))
        : Promise.resolve(mockResponse(previewApprove))
    );
  }

  test('shows the server’s reason and says the link still works', async () => {
    mockRefusal(
      { error: 'Daily invitation limit reached. Try again tomorrow.', retryable: true },
      429
    );

    renderVerify();

    expect(
      await screen.findByText('Daily invitation limit reached. Try again tomorrow.')
    ).toBeInTheDocument();
    // Not "your link died": the owner is meant to come back to this same one.
    expect(screen.getByText(/this link still works/i)).toBeInTheDocument();
    expect(screen.queryByText('Invalid or expired link.')).toBeNull();
    expect(screen.queryByText(/ask the person who invited you/i)).toBeNull();
  });

  test('a full group is a reason too, not an expiry, on the same 400 as a dead link', async () => {
    mockRefusal(
      { error: 'This collection has reached its limit of 2 guests.', retryable: true },
      400
    );

    renderVerify();

    expect(
      await screen.findByText('This collection has reached its limit of 2 guests.')
    ).toBeInTheDocument();
    expect(screen.getByText(/this link still works/i)).toBeInTheDocument();
  });

  test('a suggestion that is genuinely over is still called a dead link', async () => {
    // Same 400, same shape, no `retryable`: this RSVP was consumed and the
    // decision already stands, so the old copy is the right one — and keeping
    // it right is what stops "the link still works" from being said always.
    mockRefusal({ error: 'This suggestion is no longer pending' }, 400);

    renderVerify();

    expect(await screen.findByText('Invalid or expired link.')).toBeInTheDocument();
    expect(screen.getByText(/ask the person who invited you/i)).toBeInTheDocument();
    expect(screen.queryByText(/this link still works/i)).toBeNull();
  });
});

/**
 * Approving a suggestion is the third irreversible act on this page, and the
 * only one whose consequence lands on somebody who does not yet know they were
 * suggested: it mails a stranger an invitation. It rides the same auto-commit
 * as a booking decision — and therefore the same `committedRef` — so it owes
 * the same two guarantees, and nothing checked that it kept them.
 */
describe('the owner answering a member’s suggestion', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  const approvePreview = { requires_confirmation: true, action: 'PROPOSAL_APPROVE' };
  const approved = {
    action: 'PROPOSAL_APPROVE',
    message: 'Invitation sent',
    email: 'nou@vei.cat',
    collection_headline: 'Toy library',
  };

  function mockDecision(body) {
    globalThis.fetch = vi.fn((url, opts = {}) =>
      opts.method === 'POST'
        ? Promise.resolve(mockResponse(body))
        : Promise.resolve(mockResponse(approvePreview))
    );
  }

  test('approving names the address that was just invited', async () => {
    mockDecision(approved);

    renderVerify();

    // Naming them is the point: the owner is being told who they let into the
    // group, not merely that something happened. A confirmation that said
    // "done" would leave them unable to spot the wrong address.
    expect(await screen.findByText(/nou@vei\.cat/)).toBeInTheDocument();
    expect(screen.getByText('Confirmed!')).toBeInTheDocument();
    expect(postCalls(globalThis.fetch)).toHaveLength(1);
  });

  test('declining says the suggested person was never contacted', async () => {
    // The reassurance is the message: saying no must not read as if a stranger
    // had already been emailed and then un-emailed.
    mockDecision({ action: 'PROPOSAL_REJECT', message: 'Suggestion declined' });

    renderVerify();

    expect(await screen.findByText(/never contacted/i)).toBeInTheDocument();
    expect(screen.getByText('Declined')).toBeInTheDocument();
    expect(postCalls(globalThis.fetch)).toHaveLength(1);
  });

  test('StrictMode’s double mount never mails the invitation twice', async () => {
    // The booking decision has this test; approving needs its own, because what
    // a second commit costs here is a second email to somebody outside the app.
    mockDecision(approved);

    renderVerify(true);

    expect(await screen.findByText(/nou@vei\.cat/)).toBeInTheDocument();
    expect(getCalls(globalThis.fetch)).toHaveLength(2); // the effect really did run twice
    expect(postCalls(globalThis.fetch)).toHaveLength(1);
  });
});

describe('declining an invitation from the email', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test('is decided by the GET alone, and says the owner was told', async () => {
    // Unlike a booking, declining an invitation authorises nothing and takes
    // nothing away from anyone else, so it is safe on GET — which is exactly
    // why the page must not fire a commit of its own after it.
    globalThis.fetch = vi.fn(() =>
      Promise.resolve(mockResponse({ action: 'COLLECTION_REJECT', message: 'Invitation declined' }))
    );

    renderVerify();

    expect(
      await screen.findByText('Invitation declined. The collection owner has been notified.')
    ).toBeInTheDocument();
    expect(screen.getByText('Declined')).toBeInTheDocument();
    expect(postCalls(globalThis.fetch)).toHaveLength(0);
  });
});

/**
 * The most-travelled path in the product — every sign-in goes through it — and
 * it had no test at all. Two separate things happen here: the session is
 * written into this browser, and the **server** decides where the person lands
 * (`landing`). The second used to be decided in the page from `seenWelcome`,
 * which logout wipes, so every re-login looked like a first visit; the fix
 * moved the decision to the server and this is what keeps it there.
 */
describe('where a magic link lands', () => {
  const USER = {
    code: 'USR002',
    name: 'Lele',
    email: 'lele@test.com',
    theeeme_colors: {
      color_01: 'bus',
      color_02: 'white',
      color_03: 'engel',
      color_04: 'black',
      color_05: 'black',
      color_06: 'white',
    },
    koro: 'beat',
  };

  function Landing() {
    const { pathname, state } = useLocation();
    return <p>{`landed on ${pathname} fromInvite=${!!state?.fromInvite}`}</p>;
  }

  function renderMagicLink(body) {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve(mockResponse({ action: 'MAGIC_LINK', user: USER, ...body }))
    );
    return render(
      <MemoryRouter initialEntries={[`/verify/${CODE}`]}>
        <Routes>
          <Route path="/verify/:code" element={<VerifyPage />} />
          <Route path="*" element={<Landing />} />
        </Routes>
      </MemoryRouter>
    );
  }

  beforeEach(() => {
    localStorage.clear();
  });

  test('writes the session and drops an invited member on the collection', async () => {
    renderMagicLink({
      landing: 'collection',
      collection: 'COL001',
      invited_collection: 'COL001',
    });

    // `fromInvite` is what makes the collection show its welcome box, so the
    // two halves of this assertion are two different behaviours: the right
    // group, and arriving there as somebody who was invited.
    expect(
      await screen.findByText('landed on /collections/COL001 fromInvite=true')
    ).toBeInTheDocument();
    expect(localStorage.getItem('userCode')).toBe('USR002');
    expect(JSON.parse(localStorage.getItem('theeemeColors')).color_01).toBe('bus');
    expect(localStorage.getItem('koro')).toBe('beat');
  });

  test('a returning member with one group lands on it, but not as an invitee', async () => {
    // Same landing, no invitation: the server sends a lone-collection user
    // straight to it, and greeting them as a new arrival every time would be
    // its own small insult.
    renderMagicLink({ landing: 'collection', collection: 'COL001' });

    expect(
      await screen.findByText('landed on /collections/COL001 fromInvite=false')
    ).toBeInTheDocument();
  });

  test('anyone else goes home', async () => {
    renderMagicLink({ landing: 'home' });

    expect(await screen.findByText('landed on / fromInvite=false')).toBeInTheDocument();
  });

  /* A `landing: "welcome"` case belongs in `deployment.test.jsx`, not here: where
     it lands depends on `aboutPath`, which is null upstream and a real page on a
     deployment that replaces `src/deployment/`. Asserting this checkout's value
     writes one branch's configuration into a test the other branch then has to
     edit — a merge conflict every release, which is the trap that file opens by
     naming. Both answers are pinned there, with the module mocked. */

  test('a second person on this browser does not inherit the first one’s welcome', async () => {
    // A shared laptop. `seenWelcome` says "you have already been shown around",
    // and leaving it set would silently swallow the newcomer's first-visit box.
    localStorage.setItem('userCode', 'USR001');
    localStorage.setItem('seenWelcome', '1');

    renderMagicLink({ landing: 'home' });

    expect(await screen.findByText('landed on / fromInvite=false')).toBeInTheDocument();
    expect(localStorage.getItem('seenWelcome')).toBeNull();
    expect(localStorage.getItem('userCode')).toBe('USR002');
  });

  test('the same person signing in again keeps theirs', async () => {
    // The other half, and the one that pins the comparison rather than a blunt
    // "always clear it": re-logging in is not a first visit.
    localStorage.setItem('userCode', 'USR002');
    localStorage.setItem('seenWelcome', '1');

    renderMagicLink({ landing: 'home' });

    expect(await screen.findByText('landed on / fromInvite=false')).toBeInTheDocument();
    expect(localStorage.getItem('seenWelcome')).toBe('1');
  });
});

describe('a stalled network', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  test('gives up after 15s instead of saying "Verifying…" forever', async () => {
    // The dead end this closes: a request that never answers used to leave the
    // page on its loading screen with no error, no way out and nothing to read.
    vi.useFakeTimers();
    globalThis.fetch = vi.fn(() => new Promise(() => {})); // never settles

    renderVerify();
    expect(screen.getByText('Verifying…')).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(15000);
    });

    expect(screen.getByText('Connection error.')).toBeInTheDocument();
    expect(screen.getByText('Oops')).toBeInTheDocument();
  });

  test('a screen waiting for the person is not replaced by an error 15s later', async () => {
    /* Asserted on the delete confirmation, and not on a success screen, because
       a success screen shadows the error one in the render order and would
       have passed with both guards (the `settled` flag and its `clearTimeout`)
       torn out — a green test proving nothing.

       Here it is visible, and it is the screen where a slow read is the
       *correct* behaviour: this one asks somebody to weigh deleting their
       account. A stale timer would take the question away mid-thought and
       replace it with a connection error for a connection that answered fine. */
    vi.useFakeTimers();
    globalThis.fetch = vi.fn(() =>
      Promise.resolve(
        mockResponse({
          action: 'ACCOUNT_DELETE',
          requires_confirmation: true,
          name: 'Lele',
          email: 'lele@test.com',
          collections: 2,
          things: 5,
        })
      )
    );

    renderVerify();
    await act(async () => {}); // let the preview GET settle

    expect(screen.getByText('Delete your account?')).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(15000);
    });

    expect(screen.getByText('Delete your account?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete my account forever' })).toBeInTheDocument();
    expect(screen.queryByText('Connection error.')).toBeNull();
  });
});

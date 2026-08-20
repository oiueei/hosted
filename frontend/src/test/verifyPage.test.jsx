import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { StrictMode } from 'react';
import { vi, describe, test, expect, beforeEach } from 'vitest';
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
        : Promise.resolve(mockResponse({ requires_confirmation: true })),
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
        : Promise.resolve(mockResponse({ requires_confirmation: true })),
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
        : Promise.resolve(mockResponse({ requires_confirmation: true })),
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
        : Promise.resolve(mockResponse({ requires_confirmation: true })),
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
        : Promise.resolve(mockResponse(previewApprove)),
    );
  }

  test('shows the server’s reason and says the link still works', async () => {
    mockRefusal(
      { error: 'Daily invitation limit reached. Try again tomorrow.', retryable: true },
      429,
    );

    renderVerify();

    expect(
      await screen.findByText('Daily invitation limit reached. Try again tomorrow.'),
    ).toBeInTheDocument();
    // Not "your link died": the owner is meant to come back to this same one.
    expect(screen.getByText(/this link still works/i)).toBeInTheDocument();
    expect(screen.queryByText('Invalid or expired link.')).toBeNull();
    expect(screen.queryByText(/ask the person who invited you/i)).toBeNull();
  });

  test('a full group is a reason too, not an expiry, on the same 400 as a dead link', async () => {
    mockRefusal(
      { error: 'This collection has reached its limit of 2 guests.', retryable: true },
      400,
    );

    renderVerify();

    expect(
      await screen.findByText('This collection has reached its limit of 2 guests.'),
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

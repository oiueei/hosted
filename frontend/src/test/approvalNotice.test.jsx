import { render, screen, waitFor } from '@testing-library/react';
import { vi, describe, test, expect, beforeEach } from 'vitest';

import ApprovalNotice from '../components/ApprovalNotice';
import { isOfferable } from '../hooks/useCapabilities';

/**
 * The notice a narrowed deployment owes anyone looking at a shorter list than
 * the product has, and the predicate that shortens it.
 *
 * **Upstream it never appears.** OIUEEI withholds nothing, so every assertion
 * about it rendering is about somebody else's deployment — which is the point
 * of it living here: the React is identical in both, and a deployment narrows
 * the policy on the server without editing a form component.
 *
 * The failure it prevents is a form that quietly offers less than the product
 * does, leaving the user to conclude the feature does not exist — which, when
 * there is a page to request it on, is not even true.
 */

const MODES = [
  { value: 'PROPRIETARY', label: 'Just mine' },
  { value: 'COMMUNITY', label: 'Shared' },
];

function mockCapabilities(capabilities) {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ capabilities }) })
  );
}

beforeEach(() => {
  vi.resetModules();
  localStorage.clear();
  // The hook caches one request per signed-in account; a fresh code per test
  // keeps them independent without exporting a reset nobody would call in prod.
  localStorage.setItem('userCode', `U${Math.random()}`);
});

describe('the standalone renders nothing', () => {
  test('silent when every option is allowed', async () => {
    mockCapabilities({
      collection_modes: ['PROPRIETARY', 'COMMUNITY'],
      thing_types: [],
      request_url: null,
    });

    const { container } = render(<ApprovalNotice kind="collection_modes" catalogue={MODES} />);

    // Waiting for the fetch to settle first: asserting on an empty render
    // before it resolves would pass no matter what the answer turned out to be.
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  test('silent while the answer is unknown, and if it never arrives', async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('offline')));

    const { container } = render(<ApprovalNotice kind="collection_modes" catalogue={MODES} />);

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    // A wrong "this needs approval" on a deployment that approves everything is
    // worse than silence — the form still works, so say nothing.
    expect(container).toBeEmptyDOMElement();
  });
});

describe('a deployment that withholds something', () => {
  test('names what is missing, in the words the form used', async () => {
    mockCapabilities({
      collection_modes: ['PROPRIETARY'],
      thing_types: [],
      request_url: 'https://example.test/ask/',
    });

    render(<ApprovalNotice kind="collection_modes" catalogue={MODES} />);

    // "Shared", the label the radio would have carried — not COMMUNITY, which
    // names a database value the reader has never seen.
    expect(await screen.findByText(/Shared/)).toBeInTheDocument();
    expect(screen.queryByText(/COMMUNITY/)).not.toBeInTheDocument();
  });

  test('links to where access is requested', async () => {
    mockCapabilities({
      collection_modes: ['PROPRIETARY'],
      thing_types: [],
      request_url: 'https://example.test/ask/',
    });

    render(<ApprovalNotice kind="collection_modes" catalogue={MODES} />);

    const link = await screen.findByRole('link');
    expect(link).toHaveAttribute('href', 'https://example.test/ask/');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  test('with nowhere to ask, says so instead of inviting a request', async () => {
    mockCapabilities({ collection_modes: ['PROPRIETARY'], thing_types: [], request_url: null });

    render(<ApprovalNotice kind="collection_modes" catalogue={MODES} />);

    // "Not here" and "not yet" are different facts. Pointing someone at a
    // request page that does not exist is worse than the shortened list it
    // was meant to explain.
    expect(await screen.findByText(/not available/i)).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});

describe('isOfferable — the predicate the forms filter with', () => {
  test('offers everything while capabilities are unknown', () => {
    // Fail open: this is a courtesy to the user, never the gate. The gate is
    // the server, which refuses regardless of what the browser fetched.
    expect(isOfferable(null, 'thing_types', 'LEND_THING')).toBe(true);
  });

  test('offers what the policy allows and withholds what it does not', () => {
    const capabilities = { thing_types: ['GIFT_THING'] };

    expect(isOfferable(capabilities, 'thing_types', 'GIFT_THING')).toBe(true);
    expect(isOfferable(capabilities, 'thing_types', 'LEND_THING')).toBe(false);
  });

  test('always offers the value being edited, allowed or not', () => {
    /* Grandfathering, mirroring the server: it only judges a *change*, so a
       thing already offered under a withheld verb has to stay editable — and a
       form that dropped the current value from its own selector would display
       a different answer than the one it is about to submit. */
    const capabilities = { thing_types: ['GIFT_THING'] };

    expect(isOfferable(capabilities, 'thing_types', 'LEND_THING', 'LEND_THING')).toBe(true);
    expect(isOfferable(capabilities, 'thing_types', 'RENT_THING', 'LEND_THING')).toBe(false);
  });
});

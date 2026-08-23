import { render, screen, waitFor } from '@testing-library/react';
import { vi, describe, test, expect, beforeEach } from 'vitest';

/**
 * `useCapabilities` / `loadCapabilities` — what this deployment lets the
 * signed-in account create, fetched once and shared by every form that asks.
 *
 * The predicate on top of it (`isOfferable`) is pinned in
 * `approvalNotice.test.jsx`; this file is about the **request** underneath, and
 * the three promises its comments make that nothing was checking:
 *
 * 1. **One request per account.** Four forms consume this hook and the app
 *    already calls `/auth/me/` on load; a hook that refetched per consumer
 *    would quietly quadruple that.
 * 2. **It cannot outlive a logout.** The cache is keyed by `userCode`, so the
 *    answer for one account is never handed to whoever signs in next — the kind
 *    of leak that shows someone else's permissions.
 * 3. **A failure is not remembered.** Failing open is deliberate — the server
 *    is the gate, the UI is a courtesy — but caching the failure would turn one
 *    offline blip into a whole session of forms offering what the API refuses,
 *    ending in a 403 the user could not have predicted.
 *
 * The module caches at module scope, which is why every test re-imports it
 * after `vi.resetModules()`: there is deliberately no reset export, because
 * nothing in production would ever call it.
 */

const CAPABILITIES = {
  collection_modes: ['PROPRIETARY'],
  thing_types: ['GIFT_THING', 'SELL_THING'],
  request_url: 'https://example.org/request-access/',
};

function answerWith(capabilities) {
  return vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ capabilities }) })
  );
}

beforeEach(() => {
  vi.resetModules();
  localStorage.clear();
  localStorage.setItem('userCode', 'AAA111');
});

describe('the request is made once per account', () => {
  test('two consumers of the same session share one call', async () => {
    globalThis.fetch = answerWith(CAPABILITIES);
    const { loadCapabilities } = await import('../hooks/useCapabilities');

    const [first, second] = await Promise.all([loadCapabilities(), loadCapabilities()]);

    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    expect(first).toEqual(CAPABILITIES);
    expect(second).toEqual(CAPABILITIES);
  });

  test('an answer with no capabilities field is cached too, as no restriction', async () => {
    // A backend that does not carry the field is answering "everything", and
    // that answer is as final as any other — refetching it on every form would
    // punish the deployment that withholds nothing, which is most of them.
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ code: 'AAA111' }) })
    );
    const { loadCapabilities } = await import('../hooks/useCapabilities');

    expect(await loadCapabilities()).toBeNull();
    expect(await loadCapabilities()).toBeNull();
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });
});

describe('the cache cannot outlive the account it answered for', () => {
  test('a different signed-in user gets their own answer, not the previous one', async () => {
    const other = { collection_modes: ['COMMUNITY'], thing_types: [], request_url: null };
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ capabilities: CAPABILITIES }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ capabilities: other }),
      });
    const { loadCapabilities } = await import('../hooks/useCapabilities');

    expect(await loadCapabilities()).toEqual(CAPABILITIES);

    // What a logout leaves behind: LogoutPage clears userCode, and the next
    // person signs in under their own.
    localStorage.setItem('userCode', 'BBB222');

    expect(await loadCapabilities()).toEqual(other);
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });
});

describe('a failed request is not remembered', () => {
  test('a network error resolves to null and the next form retries', async () => {
    globalThis.fetch = vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ capabilities: CAPABILITIES }),
      });
    const { loadCapabilities } = await import('../hooks/useCapabilities');

    // Fail open: null, which every caller reads as "no restriction".
    expect(await loadCapabilities()).toBeNull();
    // And not sticky: the next form asks again and gets the real answer.
    expect(await loadCapabilities()).toEqual(CAPABILITIES);
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  test('a non-OK response is a failure, not an answer of "no restrictions"', async () => {
    // A 500 says nothing about what this deployment allows. Treating it as an
    // empty answer is what made the blip stick.
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 500, json: () => Promise.resolve({}) })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ capabilities: CAPABILITIES }),
      });
    const { loadCapabilities } = await import('../hooks/useCapabilities');

    expect(await loadCapabilities()).toBeNull();
    expect(await loadCapabilities()).toEqual(CAPABILITIES);
  });
});

describe('the hook hands the answer to a component', () => {
  test('null until known, then the capabilities', async () => {
    globalThis.fetch = answerWith(CAPABILITIES);
    const { default: useCapabilities } = await import('../hooks/useCapabilities');

    function Probe() {
      const capabilities = useCapabilities();
      return <p>{capabilities ? capabilities.thing_types.join(',') : 'unknown'}</p>;
    }

    render(<Probe />);

    // The first paint has no answer yet, and every consumer treats that as no
    // restriction rather than blocking on it.
    expect(screen.getByText('unknown')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('GIFT_THING,SELL_THING')).toBeInTheDocument());
  });
});

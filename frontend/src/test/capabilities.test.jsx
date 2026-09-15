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
 * after `vi.resetModules()` rather than relying on `invalidateMe()` (below) to
 * reset between tests — that export exists for one specific production
 * caller (`EditProfilePage`, after a language save), not as a test seam.
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

describe('loadUserLanguage', () => {
  test('never fetches for a signed-out visitor', async () => {
    // Every pre-existing caller of the shared cache (`loadCapabilities`) only
    // ever ran from a page behind RequireAuth, so `apiFetch`'s 401-then-
    // refresh-then-redirect-to-/login dance never fired for a signed-out
    // visitor in practice. `useCollectionLanguage` is the first caller reached
    // from genuinely public pages (a collection/thing page anyone can open),
    // so without this guard, opening one for a collection with a `language`
    // set would silently hard-navigate every anonymous visitor to `/login`
    // (found in review, 2026-09-15).
    localStorage.removeItem('userCode');
    globalThis.fetch = answerWith(CAPABILITIES);
    const { loadUserLanguage } = await import('../hooks/useCapabilities');

    expect(await loadUserLanguage()).toBe('');
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  test('a stale userCode with a dead session answers the empty string, never redirects', async () => {
    // `userCode` never expires on its own; the cookies behind it do
    // (access_token 1h, refresh_token 7d — core/views/auth.py). A visitor who
    // signed in over a week ago and comes back still has `userCode`, so the
    // guard in the previous test alone does not catch them — every fetch here
    // 401s (the second call is `apiFetch`'s own refresh attempt, which still
    // runs even with `optionalAuth`; only the *redirect on its failure* is
    // what `optionalAuth` suppresses). Nothing on a public collection/thing/
    // share page could ever 401 before this feature (found in review,
    // 2026-09-15). Without `optionalAuth: true` on the shared fetch, `apiFetch`
    // would clear `userCode` and hard-navigate to `/login` right here — so
    // `userCode` surviving is the one proxy this test can check for that
    // (jsdom does not implement real navigation, so `window.location` itself
    // cannot be asserted on).
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({}) })
    );
    const { loadUserLanguage } = await import('../hooks/useCapabilities');

    await expect(loadUserLanguage()).resolves.toBe('');
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
    expect(localStorage.getItem('userCode')).toBe('AAA111');
  });

  test('shares the cached request with loadCapabilities — one call answers both', async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ capabilities: CAPABILITIES, language: 'ca' }),
      })
    );
    const { loadCapabilities, loadUserLanguage } = await import('../hooks/useCapabilities');

    const [capabilities, language] = await Promise.all([loadCapabilities(), loadUserLanguage()]);

    expect(capabilities).toEqual(CAPABILITIES);
    expect(language).toBe('ca');
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  test('a signed-in account with no saved language answers the empty string', async () => {
    globalThis.fetch = answerWith(CAPABILITIES);
    const { loadUserLanguage } = await import('../hooks/useCapabilities');

    expect(await loadUserLanguage()).toBe('');
  });

  test('a failed request is not remembered, same as loadCapabilities', async () => {
    globalThis.fetch = vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ language: 'ca' }),
      });
    const { loadUserLanguage } = await import('../hooks/useCapabilities');

    expect(await loadUserLanguage()).toBe('');
    expect(await loadUserLanguage()).toBe('ca');
  });
});

describe('invalidateMe', () => {
  test('drops the cache so the next call re-fetches instead of serving a stale language', async () => {
    // `language` changes from inside the SPA (EditProfilePage), unlike
    // `capabilities`. Without this, a member who opened a collection (caching
    // their pre-edit language) and then saved a new one in their profile
    // would see the stale value again on their very next visit to any
    // collection — self-healing only on a full reload (found in review,
    // 2026-09-15).
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ language: 'es' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ language: 'ca' }),
      });
    const { loadUserLanguage, invalidateMe } = await import('../hooks/useCapabilities');

    expect(await loadUserLanguage()).toBe('es');
    expect(await loadUserLanguage()).toBe('es'); // still cached
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);

    invalidateMe();

    expect(await loadUserLanguage()).toBe('ca');
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });
});

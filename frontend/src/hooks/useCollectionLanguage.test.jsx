import { render, waitFor, act } from '@testing-library/react';
import { useEffect, useState } from 'react';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

/**
 * `useCollectionLanguage` — the hierarchy CA settled on (2026-09-15, mirrors
 * the email-side `resolve_email_language`): a signed-in visitor's own
 * deliberately-saved language always wins; failing that, the collection they
 * are looking at; failing that, the plain browser/localStorage default,
 * unchanged.
 *
 * The trap this hook exists to avoid is the frontend twin of the bug just
 * fixed server-side (`join-language-stamp-bug`): `i18next-browser-
 * languagedetector` caches whatever `changeLanguage()` is called with into
 * `localStorage['i18nextLng']`, and reads that cache back on the *next* boot
 * as if it were a deliberate choice. Applying a collection's language via a
 * plain `changeLanguage()` call would therefore silently make the first
 * collection a fresh visitor happens to land on their permanent browser
 * default everywhere else too. Every test below that applies or reverts an
 * override checks the cache came back exactly as it found it, not just that
 * `i18n.language` moved.
 */

vi.mock('./useCapabilities', () => ({ loadUserLanguage: vi.fn() }));

import i18n from '../i18n';
import { loadUserLanguage } from './useCapabilities';
import useCollectionLanguage from './useCollectionLanguage';

function Probe({ collectionLanguage }) {
  useCollectionLanguage(collectionLanguage);
  const [lang, setLang] = useState(i18n.language);
  useEffect(() => {
    const handler = (lng) => setLang(lng);
    i18n.on('languageChanged', handler);
    return () => i18n.off('languageChanged', handler);
  }, []);
  return <p>{lang}</p>;
}

function Wrapper({ mounted, collectionLanguage }) {
  return mounted ? <Probe collectionLanguage={collectionLanguage} /> : null;
}

const STORAGE_KEY = 'i18nextLng';

beforeEach(async () => {
  vi.clearAllMocks();
  loadUserLanguage.mockResolvedValue('');
  localStorage.clear();
  await act(async () => {
    await i18n.changeLanguage('en');
  });
  // The reset above re-caches 'en' as a real choice — clear it back out so
  // each test starts from the same "nothing cached yet" baseline the app
  // itself starts a fresh visitor from.
  localStorage.removeItem(STORAGE_KEY);
});

afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage('en');
  });
  localStorage.removeItem(STORAGE_KEY);
});

describe('no collection language', () => {
  test('does nothing at all — the browser default stands', async () => {
    render(<Wrapper mounted collectionLanguage="" />);

    await waitFor(() => expect(loadUserLanguage).not.toHaveBeenCalled());
    expect(i18n.language).toBe('en');
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  test('an unsupported code is treated the same as none — no fetch, no override', async () => {
    render(<Wrapper mounted collectionLanguage="fr" />);

    await new Promise((resolve) => setTimeout(resolve, 10));
    // Never even asks who the visitor is: pointless for a code the hook could
    // not apply anyway, and every truthy `collectionLanguage` used to fetch
    // `/auth/me/` regardless — the exact call an anonymous visitor must never
    // make (found in review, 2026-09-15; see `useCapabilities.loadUserLanguage`).
    expect(loadUserLanguage).not.toHaveBeenCalled();
    expect(i18n.language).toBe('en');
  });
});

describe('a visitor with no preference of their own', () => {
  test('adopts the collection language without polluting the persisted cache', async () => {
    loadUserLanguage.mockResolvedValue('');
    render(<Wrapper mounted collectionLanguage="ca" />);

    await waitFor(() => expect(i18n.language).toBe('ca'));
    // The whole point: the next boot must not see this as a deliberate pick.
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  test('reverts to the language it found, restoring the cache exactly as it was', async () => {
    // Simulate a visitor who *does* have something explicitly cached already
    // (e.g. picked English once) so the "restore" path is exercised, not just
    // the "there was nothing to restore" one.
    localStorage.setItem(STORAGE_KEY, 'en');
    loadUserLanguage.mockResolvedValue('');
    const { rerender } = render(<Wrapper mounted collectionLanguage="ca" />);

    await waitFor(() => expect(i18n.language).toBe('ca'));
    expect(localStorage.getItem(STORAGE_KEY)).toBe('en');

    await act(async () => {
      rerender(<Wrapper mounted={false} collectionLanguage="ca" />);
      await new Promise((resolve) => setTimeout(resolve, 10));
    });

    await waitFor(() => expect(i18n.language).toBe('en'));
    expect(localStorage.getItem(STORAGE_KEY)).toBe('en');
  });

  test('reverts with nothing cached, leaving nothing cached — a leaked write would show up here', async () => {
    // The previous test seeds the key with the SAME value the revert target
    // would itself produce if the cleanup ever leaked its own `changeLanguage`
    // write, so it cannot distinguish "restored correctly" from "wrote 'en'
    // again by accident". Starting from *absent* can.
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    loadUserLanguage.mockResolvedValue('');
    const { rerender } = render(<Wrapper mounted collectionLanguage="ca" />);

    await waitFor(() => expect(i18n.language).toBe('ca'));
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();

    await act(async () => {
      rerender(<Wrapper mounted={false} collectionLanguage="ca" />);
      await new Promise((resolve) => setTimeout(resolve, 10));
    });

    await waitFor(() => expect(i18n.language).toBe('en'));
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  test("restores the cache before changeLanguage's own promise settles, not just eventually", async () => {
    // `ca`'s translation file is a lazy `import()` (`i18n/index.js`), so
    // `changeLanguage('ca')`'s returned promise does not resolve on this same
    // tick — but `i18next` caches the new language into `localStorage`
    // *synchronously*, inside the call itself, before that promise settles
    // (verified against the real i18next source in review). A restore
    // chained only onto `.then()` would leave the wrong value sitting in
    // `localStorage` for the whole chunk download. `i18n.changeLanguage` is
    // replaced here with a stand-in that reproduces exactly that one fact —
    // a synchronous cache write, then a promise this test controls — so the
    // assertion below does not depend on how many real microtasks a dynamic
    // import happens to take.
    loadUserLanguage.mockResolvedValue('');
    let resolveChange;
    const spy = vi.spyOn(i18n, 'changeLanguage').mockImplementation((lng) => {
      localStorage.setItem(STORAGE_KEY, lng);
      return new Promise((resolve) => {
        resolveChange = resolve;
      });
    });

    render(<Wrapper mounted collectionLanguage="ca" />);
    await waitFor(() => expect(spy).toHaveBeenCalledWith('ca'));

    // The stand-in's own write already landed; its promise has not resolved
    // yet. Restoring only in `.then()` would still show 'ca' here.
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();

    resolveChange();
    spy.mockRestore();
  });
});

describe('a visitor with a deliberate preference of their own', () => {
  test('is left alone — the collection language never applies', async () => {
    loadUserLanguage.mockResolvedValue('es');
    render(<Wrapper mounted collectionLanguage="ca" />);

    await waitFor(() => expect(loadUserLanguage).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(i18n.language).toBe('en');
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});

describe('already matching', () => {
  test('does not call changeLanguage when the UI is already in that language', async () => {
    await act(async () => {
      await i18n.changeLanguage('ca');
    });
    localStorage.removeItem(STORAGE_KEY);
    const spy = vi.spyOn(i18n, 'changeLanguage');
    loadUserLanguage.mockResolvedValue('');

    render(<Wrapper mounted collectionLanguage="ca" />);

    await waitFor(() => expect(loadUserLanguage).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});

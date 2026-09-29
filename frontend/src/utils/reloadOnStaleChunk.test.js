import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

import { installStaleChunkReload, STALE_CHUNK_KEY, RELOAD_WINDOW_MS } from './reloadOnStaleChunk';

/**
 * A tab open across a deploy asks for a lazy chunk that is gone. The reload that
 * cures it must happen once, and must never become a loop when the chunk is
 * *still* missing after the reload.
 *
 * The window and the storage are injected, so the reload is a spy and the
 * "browser" is an `EventTarget`: jsdom cannot really navigate, and the only
 * thing worth pinning is when the module reloads and when it lets the error
 * through to the `ErrorBoundary`.
 */

// The event is handed straight to the listener rather than through a real
// `EventTarget`: jsdom swallows whatever a listener throws (it reports it and moves
// on), and a try/catch that was missed must fail the test, not scroll past in stderr.
const fakeWindow = (extra = {}) => {
  const listeners = new Map();
  const win = {
    location: { reload: vi.fn() },
    addEventListener: (type, fn) => listeners.set(type, fn),
    removeEventListener: (type, fn) => {
      if (listeners.get(type) === fn) listeners.delete(type);
    },
    dispatchEvent: (event) => {
      listeners.get(event.type)?.(event);
      return !event.defaultPrevented;
    },
  };
  return Object.assign(win, extra);
};

const fakeStorage = (initial = {}) => {
  const data = { ...initial };
  return {
    data,
    getItem: (key) => data[key] ?? null,
    setItem: (key, value) => {
      data[key] = String(value);
    },
  };
};

// Vite's event: cancelable, and the page only survives it if it is prevented.
const preloadError = (win) => {
  const event = new Event('vite:preloadError', { cancelable: true });
  win.dispatchEvent(event);
  return event;
};

const NOW = new Date('2026-09-29T12:00:00Z');

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('a missing chunk', () => {
  test('reloads the page, and keeps the error from being thrown', () => {
    const win = fakeWindow();
    const storage = fakeStorage();
    installStaleChunkReload(win, storage);

    const event = preloadError(win);

    expect(win.location.reload).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
    expect(storage.data[STALE_CHUNK_KEY]).toBe(String(NOW.getTime()));
  });

  test('a second failure right after is left to the ErrorBoundary — no reload loop', () => {
    const win = fakeWindow();
    installStaleChunkReload(win, fakeStorage());
    preloadError(win);

    vi.advanceTimersByTime(2_000);
    const second = preloadError(win);

    expect(win.location.reload).toHaveBeenCalledTimes(1);
    // Not prevented: the error is thrown, and the boundary shows its fallback.
    expect(second.defaultPrevented).toBe(false);
  });

  test('reloads again once the window has passed — a later deploy is a new case', () => {
    const win = fakeWindow();
    const storage = fakeStorage();
    installStaleChunkReload(win, storage);
    preloadError(win);

    vi.advanceTimersByTime(RELOAD_WINDOW_MS);
    const later = preloadError(win);

    expect(win.location.reload).toHaveBeenCalledTimes(2);
    expect(later.defaultPrevented).toBe(true);
    expect(storage.data[STALE_CHUNK_KEY]).toBe(String(Date.now()));
  });

  test('the window closes to the millisecond', () => {
    const win = fakeWindow();
    installStaleChunkReload(win, fakeStorage());
    preloadError(win);

    vi.advanceTimersByTime(RELOAD_WINDOW_MS - 1);
    preloadError(win);
    expect(win.location.reload).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(1);
    preloadError(win);
    expect(win.location.reload).toHaveBeenCalledTimes(2);
  });

  test('a mark from the future does not hold the guard shut', () => {
    // A clock moved back: the stamp is ahead of `now` and must not read as "just now".
    const win = fakeWindow();
    installStaleChunkReload(win, fakeStorage({ [STALE_CHUNK_KEY]: String(Date.now() + 60_000) }));

    preloadError(win);

    expect(win.location.reload).toHaveBeenCalledTimes(1);
  });

  test('an unreadable mark counts as no earlier reload', () => {
    const win = fakeWindow();
    installStaleChunkReload(win, fakeStorage({ [STALE_CHUNK_KEY]: 'not a number' }));

    preloadError(win);

    expect(win.location.reload).toHaveBeenCalledTimes(1);
  });
});

describe('when the mark cannot be kept, the page is not reloaded — that would be the loop', () => {
  test('storage that throws on read', () => {
    const win = fakeWindow();
    installStaleChunkReload(win, {
      getItem: () => {
        throw new Error('SecurityError');
      },
      setItem: () => {},
    });

    const event = preloadError(win);

    expect(win.location.reload).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  test('storage that throws on write (quota, private mode)', () => {
    const win = fakeWindow();
    installStaleChunkReload(win, {
      getItem: () => null,
      setItem: () => {
        throw new Error('QuotaExceededError');
      },
    });

    const event = preloadError(win);

    expect(win.location.reload).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  test('a window whose sessionStorage cannot even be touched: installing is safe, the error passes', () => {
    const win = fakeWindow();
    Object.defineProperty(win, 'sessionStorage', {
      get() {
        throw new DOMException('denied', 'SecurityError');
      },
    });

    // Installing runs before the app renders: it must not be what breaks it.
    expect(() => installStaleChunkReload(win)).not.toThrow();
    const event = preloadError(win);

    expect(win.location.reload).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });
});

describe('the default storage', () => {
  test("is the window's own sessionStorage", () => {
    const sessionStorage = fakeStorage();
    const win = fakeWindow({ sessionStorage });
    installStaleChunkReload(win);

    preloadError(win);

    expect(win.location.reload).toHaveBeenCalledTimes(1);
    expect(sessionStorage.data[STALE_CHUNK_KEY]).toBe(String(NOW.getTime()));
  });
});

describe('uninstalling', () => {
  test('the returned function stops listening', () => {
    const win = fakeWindow();
    const uninstall = installStaleChunkReload(win, fakeStorage());

    uninstall();
    const event = preloadError(win);

    expect(win.location.reload).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });
});

import { act } from '@testing-library/react';
import { vi } from 'vitest';

/** The breakpoint the app switches its markup at: below `breakpoint-m` (768px). */
export const PHONE = '(max-width: 767px)';
export const REDUCED_MOTION = '(prefers-reduced-motion: reduce)';

/**
 * jsdom has no `window.matchMedia`. This puts one there for a test: every query
 * answers what `initial` says (`{ [PHONE]: true }`), anything unlisted answers
 * `false`, and `set(query, matches)` flips an answer and tells whoever is
 * listening, as a browser does when a window crosses a breakpoint.
 *
 * Call `restore()` afterwards (an `afterEach`): leaving the stub behind would
 * turn every later test in the file into a phone.
 */
export function mockMatchMedia(initial = {}) {
  const answers = { ...initial };
  const listeners = new Map();
  const original = window.matchMedia;

  window.matchMedia = vi.fn((query) => ({
    get matches() {
      return Boolean(answers[query]);
    },
    media: query,
    addEventListener: (type, fn) => {
      if (type !== 'change') return;
      if (!listeners.has(query)) listeners.set(query, new Set());
      listeners.get(query).add(fn);
    },
    removeEventListener: (type, fn) => {
      if (type === 'change') listeners.get(query)?.delete(fn);
    },
  }));

  return {
    set(query, matches) {
      answers[query] = matches;
      act(() => listeners.get(query)?.forEach((fn) => fn({ matches, media: query })));
    },
    listening: (query) => listeners.get(query)?.size ?? 0,
    restore() {
      if (original === undefined) delete window.matchMedia;
      else window.matchMedia = original;
    },
  };
}

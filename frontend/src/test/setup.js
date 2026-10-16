import '@testing-library/jest-dom';
import { cleanup, configure } from '@testing-library/react';
import { afterEach } from 'vitest';
import nodeConsole from 'node:console';
import './i18n-mock';

// findBy*/waitFor default to 1s, which pages with chained async fetches
// (ThingPage → FAQs → transfers) can exceed under CI CPU load. 5s only
// delays genuine failures, never passes.
configure({ asyncUtilTimeout: 5000 });

// Minimal localStorage mock for jsdom
const store = {};
const localStorageMock = {
  getItem: (key) => store[key] ?? null,
  setItem: (key, value) => {
    store[key] = String(value);
  },
  removeItem: (key) => {
    delete store[key];
  },
  clear: () => {
    Object.keys(store).forEach((k) => delete store[k]);
  },
};
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock });

// Suppress CSS.supports errors from HDS in jsdom
if (!globalThis.CSS) {
  globalThis.CSS = { supports: () => false };
}

// HDS components (Select, TextArea) require ResizeObserver
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// jsdom can't parse HDS's CSS and logs this on every stylesheet import —
// harmless, but it buries real failures in CI output. Drop only this
// message; everything else still reaches console.error. jsdom's
// VirtualConsole forwards to the *original* node:console object it was
// handed at environment setup, ahead of Vitest's own console wrapper, so
// that's the object that actually needs patching (patching globalThis.console
// alone leaves this one call site un-intercepted).
//
// React's "not wrapped in act(...)" warnings are not noise: each one is a state
// update that landed while nobody was watching, so a test that ends before it, or
// asserts around it, is not testing what the page does. They are collected here and
// fail the test that produced them (below), rather than burying the day one of
// them matters under hundreds that do not.
const actWarnings = [];

function withoutKnownNoise(original) {
  return (...args) => {
    if (typeof args[0] === 'string') {
      if (args[0].includes('Could not parse CSS stylesheet')) return;
      if (args[0].includes('not wrapped in act')) {
        // "An update to %s inside a test…" carries the component's name as its argument.
        actWarnings.push(args[0].split('\n')[0].replace('%s', String(args[1] ?? 'a component')));
      }
    }
    original(...args);
  };
}
nodeConsole.error = withoutKnownNoise(nodeConsole.error);
console.error = withoutKnownNoise(console.error);

afterEach(() => {
  if (actWarnings.length === 0) return;
  const found = actWarnings.splice(0);
  // A hook that throws stops the ones after it, and Testing Library's own cleanup is
  // one of them: without this the failed test's DOM stays and breaks the next tests
  // with causes that are not theirs.
  cleanup();
  throw new Error(
    `${found.length} state update(s) outside act(...) — wait for the final state ` +
      `(findBy…, or \`settle\` from src/test/settle.js) before the test ends:\n` +
      found.map((warning) => `  ${warning}`).join('\n')
  );
});

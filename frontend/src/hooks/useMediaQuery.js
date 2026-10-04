import { useCallback, useSyncExternalStore } from 'react';

/**
 * Whether a CSS media query matches right now, and again whenever that changes
 * (a phone turned on its side, a window dragged across 768px).
 *
 * For the places where the *markup* has to differ below a breakpoint — not just
 * its style: a table that turns into a list of cards (`ResponsiveTable`) must
 * paint one thing or the other, never both, or a screen reader reads every row
 * twice. A difference that CSS alone can express stays in the stylesheet.
 *
 * Where there is no `window.matchMedia` (jsdom, which the test suite runs in) the
 * answer is `false`, so a component reading `(max-width: 767px)` paints its
 * desktop form there and the tests written for it keep seeing that form.
 *
 * Built on `useSyncExternalStore`, so the value is read from the browser during
 * render rather than copied into state after it: no first paint with the wrong
 * layout followed by a correction.
 */
export default function useMediaQuery(query) {
  const supported = () => typeof window !== 'undefined' && typeof window.matchMedia === 'function';

  const subscribe = useCallback(
    (onChange) => {
      if (!supported()) return () => {};
      const list = window.matchMedia(query);
      list.addEventListener('change', onChange);
      return () => list.removeEventListener('change', onChange);
    },
    [query]
  );

  return useSyncExternalStore(
    subscribe,
    () => supported() && window.matchMedia(query).matches,
    () => false
  );
}

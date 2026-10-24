import { renderHook } from '@testing-library/react';
import useCollectionTheeeme from '../hooks/useCollectionTheeeme';

/**
 * Make `colors` (and `koro`) the palette in force, as a collection's page does with
 * `useCollectionTheeeme`, for the page the test renders next.
 *
 * The palette is a small global store, so a declaration mounted in a tree of its own
 * reaches every reader in the test; it is withdrawn when the test's cleanup unmounts
 * it. It replaces what tests used to do — put the colours in `localStorage` — which
 * the app no longer reads.
 */
export default function declarePalette(colors, koro) {
  return renderHook(() => useCollectionTheeeme(colors, koro));
}

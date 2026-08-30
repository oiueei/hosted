/**
 * A live region that is already there when the message arrives.
 *
 * HDS gives a `Notification` `role="alert"` **only** when it is positioned — a
 * toast. An inline one gets no role at all, so of the 42 in this app exactly one
 * was ever announced. Press Save, have it fail, and a screen reader said nothing:
 * the error was on screen and nowhere else. That is WCAG 4.1.3 Status Messages,
 * level AA, and it is not something a page can be tested into after the fact —
 * a live region only announces changes made *inside a region that already
 * existed*, so wrapping the message at the moment it appears would do nothing.
 *
 * Hence the shape: this renders unconditionally, and the conditional stays
 * inside it.
 *
 *     <StatusRegion>{saved && <Notification …/>}</StatusRegion>
 *
 * `role="status"` (polite) rather than `alert` (assertive) throughout, including
 * for errors. These messages answer something the reader just did, so they can
 * wait for the current utterance to finish; assertive interrupts mid-word and is
 * for things that cannot. It also keeps one region able to hold either outcome —
 * most of these slots carry `type={result.type}` and swap between success and
 * error, and changing a region's politeness while it is live is unreliable.
 *
 * Not for a message that *is* the page — a load error rendered on mount is read
 * in document order like any other content, and announcing it would say it twice.
 */
export default function StatusRegion({ children }) {
  return (
    <div role="status" className="status-region">
      {children}
    </div>
  );
}

import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, test, expect } from 'vitest';
import ImageCarousel from './ImageCarousel';

const THREE = ['a.jpg', 'b.jpg', 'c.jpg'];

function renderCarousel(props = {}) {
  return render(
    <MemoryRouter>
      <ImageCarousel images={THREE} alt="My Thing" {...props} />
    </MemoryRouter>
  );
}

const prev = () => screen.getByRole('button', { name: 'Previous image' });
const next = () => screen.getByRole('button', { name: 'Next image' });
const shownSrc = () => document.querySelector('.image-carousel-image').getAttribute('src');

describe('ImageCarousel navigation', () => {
  test('the arrows walk the gallery and stop at both ends', () => {
    renderCarousel();
    expect(shownSrc()).toBe('a.jpg');

    fireEvent.click(next());
    expect(shownSrc()).toBe('b.jpg');
    fireEvent.click(next());
    expect(shownSrc()).toBe('c.jpg');

    // Non-cyclic by design: the last image must not wrap round to the first,
    // or a reader loses track of how many photos there are.
    fireEvent.click(next());
    expect(shownSrc()).toBe('c.jpg');

    fireEvent.click(prev());
    fireEvent.click(prev());
    expect(shownSrc()).toBe('a.jpg');
    fireEvent.click(prev());
    expect(shownSrc()).toBe('a.jpg');
  });

  test('arrow keys move through the gallery from a focused arrow', () => {
    renderCarousel();
    // The handler sits on the carousel group; the keypress reaches it by
    // bubbling from whichever arrow the user has tabbed to.
    fireEvent.keyDown(next(), { key: 'ArrowRight' });
    expect(shownSrc()).toBe('b.jpg');
    fireEvent.keyDown(next(), { key: 'ArrowLeft' });
    expect(shownSrc()).toBe('a.jpg');
  });
});

describe('ImageCarousel keyboard', () => {
  test('the keys stop at both ends, like the arrows', () => {
    renderCarousel();

    // ArrowLeft on the first photo has nowhere to go.
    fireEvent.keyDown(prev(), { key: 'ArrowLeft' });
    expect(shownSrc()).toBe('a.jpg');

    fireEvent.keyDown(next(), { key: 'ArrowRight' });
    fireEvent.keyDown(next(), { key: 'ArrowRight' });
    expect(shownSrc()).toBe('c.jpg');
    // ...nor does ArrowRight on the last: it must not wrap to the first.
    fireEvent.keyDown(next(), { key: 'ArrowRight' });
    expect(shownSrc()).toBe('c.jpg');
  });

  test('an arrow key is consumed — the page behind does not scroll sideways as well', () => {
    renderCarousel();

    // `fireEvent` returns false when the event's default was prevented.
    expect(fireEvent.keyDown(next(), { key: 'ArrowRight' })).toBe(false);
    expect(fireEvent.keyDown(prev(), { key: 'ArrowLeft' })).toBe(false);
  });

  test('any other key leaves the photo alone and the browser its default', () => {
    renderCarousel();

    for (const key of ['ArrowUp', 'ArrowDown', 'Enter', 'a', 'Tab']) {
      // Not prevented: Tab must still leave the group, and typing must still type.
      expect(fireEvent.keyDown(next(), { key }), key).toBe(true);
    }
    expect(shownSrc()).toBe('a.jpg');
  });
});

describe('ImageCarousel swiping', () => {
  // A finger drag on the photo: where it lands in `touchstart`, where it lifts in `touchend`.
  const swipe = (from, to) => {
    const photo = screen.getByRole('img');
    fireEvent.touchStart(photo, { touches: [{ clientX: from }] });
    fireEvent.touchEnd(photo, { changedTouches: [{ clientX: to }] });
  };

  test('dragging left brings the next photo, dragging right the previous', () => {
    renderCarousel();

    swipe(300, 100); // the content follows the finger: left is forward
    expect(shownSrc()).toBe('b.jpg');
    swipe(100, 300);
    expect(shownSrc()).toBe('a.jpg');
  });

  test('a swipe stops at the ends, it does not wrap', () => {
    renderCarousel();

    swipe(100, 300); // right on the first photo
    expect(shownSrc()).toBe('a.jpg');

    swipe(300, 100);
    swipe(300, 100);
    expect(shownSrc()).toBe('c.jpg');
    swipe(300, 100); // left on the last
    expect(shownSrc()).toBe('c.jpg');
  });

  test('a drag of 40px or less is a tap or a slip, not a swipe; more than that is', () => {
    renderCarousel();

    swipe(200, 160); // exactly 40 to the left
    expect(shownSrc()).toBe('a.jpg');
    swipe(200, 159); // 41
    expect(shownSrc()).toBe('b.jpg');

    swipe(200, 240); // exactly 40 to the right
    expect(shownSrc()).toBe('b.jpg');
    swipe(200, 241); // 41
    expect(shownSrc()).toBe('a.jpg');
  });

  test('a touch that ends here but began elsewhere does nothing', () => {
    renderCarousel();
    // From the second photo, so that a phantom swipe could go either way.
    fireEvent.click(next());
    expect(shownSrc()).toBe('b.jpg');

    // No `touchstart` on the photo: the finger came in from outside it. (Far from 0 on
    // purpose: the guard's absence would read a missing start as 0 and swipe backwards.)
    fireEvent.touchEnd(screen.getByRole('img'), { changedTouches: [{ clientX: 300 }] });

    expect(shownSrc()).toBe('b.jpg');
  });

  test('one swipe moves one photo, however many `touchend`s follow it', () => {
    renderCarousel();
    const photo = screen.getByRole('img');
    fireEvent.touchStart(photo, { touches: [{ clientX: 300 }] });
    fireEvent.touchEnd(photo, { changedTouches: [{ clientX: 100 }] });
    expect(shownSrc()).toBe('b.jpg');

    // The start is spent by the first end; a stray second one has none to measure from.
    fireEvent.touchEnd(photo, { changedTouches: [{ clientX: 100 }] });

    expect(shownSrc()).toBe('b.jpg');
  });

  test('the live region announces the photo a swipe arrives at', () => {
    renderCarousel();
    const photo = screen.getByRole('img');
    fireEvent.touchStart(photo, { touches: [{ clientX: 300 }] });
    fireEvent.touchEnd(photo, { changedTouches: [{ clientX: 100 }] });

    expect(document.querySelector('.image-carousel [aria-live="polite"]')).toHaveTextContent(
      /image 2 of 3/i
    );
  });
});

describe('ImageCarousel variants', () => {
  test('the card variant sizes the group and the photo for the collection grid', () => {
    const { container } = renderCarousel({ variant: 'card' });

    expect(container.querySelector('[role="group"]')).toHaveClass('image-carousel--card');
    expect(screen.getByRole('img')).toHaveClass('image-carousel-image--card');
    expect(screen.getByRole('img')).not.toHaveClass('detail-image');
  });

  test('the default, detail variant is the page-sized photo', () => {
    const { container } = renderCarousel();

    expect(container.querySelector('[role="group"]')).not.toHaveClass('image-carousel--card');
    expect(screen.getByRole('img')).toHaveClass('detail-image');
  });
});

describe('ImageCarousel end-of-gallery focus', () => {
  // Why the assertion is on the attribute rather than on document.activeElement:
  // the failure being guarded is a *browser* behaviour — disabling the element
  // that currently holds focus makes the browser move focus to <body>, which
  // costs the reader their tab position and, because the ArrowLeft/ArrowRight
  // handler lives on the carousel group, silently stops the keyboard working.
  // jsdom does not implement that blur-on-disable, so a focus-based test here
  // passes with `disabled` too and would certify nothing. The attribute is the
  // real, checkable contract: a spent arrow must be `aria-disabled` and must
  // never carry `disabled`.
  test('a spent arrow is aria-disabled, never disabled, and stays focusable', () => {
    renderCarousel();

    expect(prev()).toHaveAttribute('aria-disabled', 'true');
    expect(prev()).not.toHaveAttribute('disabled');
    prev().focus();
    expect(document.activeElement).toBe(prev());

    // Announced as unavailable and inert when pressed — without being removed
    // from the tab order.
    fireEvent.click(prev());
    expect(shownSrc()).toBe('a.jpg');
  });

  test('the far arrow becomes spent only on reaching the far end', () => {
    renderCarousel();

    expect(next()).toHaveAttribute('aria-disabled', 'false');
    fireEvent.click(next());
    fireEvent.click(next());
    expect(shownSrc()).toBe('c.jpg');
    expect(next()).toHaveAttribute('aria-disabled', 'true');
    expect(next()).not.toHaveAttribute('disabled');
    expect(prev()).toHaveAttribute('aria-disabled', 'false');
  });
});

describe('ImageCarousel accessible announcement', () => {
  test('the live region tracks the position through the gallery', () => {
    renderCarousel();
    const live = document.querySelector('.image-carousel [aria-live="polite"]');

    expect(live).toHaveTextContent(/image 1 of 3/i);
    fireEvent.click(next());
    expect(live).toHaveTextContent(/image 2 of 3/i);
  });

  test('an empty gallery renders nothing rather than an empty frame', () => {
    const { container } = render(
      <MemoryRouter>
        <ImageCarousel images={[]} alt="My Thing" />
      </MemoryRouter>
    );
    expect(container.querySelector('.image-carousel')).toBeNull();
  });
});

describe('ImageCarousel as a link', () => {
  test('the image links to the thing while the arrows only change the photo', () => {
    const { container } = renderCarousel({ to: '/things/ABC123' });

    // The photo is the navigation target for a pointer...
    expect(container.querySelector('a')).toHaveAttribute('href', '/things/ABC123');

    // ...but paging must not navigate, or browsing photos would leave the page.
    fireEvent.click(next());
    expect(shownSrc()).toBe('b.jpg');
    expect(container.querySelector('a')).toHaveAttribute('href', '/things/ABC123');
  });

  test('that link costs no tab stop and is announced by nobody', () => {
    // It repeats a destination the caller already links to by name — the thing's
    // headline — so leaving it in the tab order gave every card two stops to the
    // same place, and a screen reader two entries under the same words.
    const { container } = renderCarousel({ to: '/things/ABC123' });

    const link = container.querySelector('a');
    expect(link).toHaveAttribute('tabindex', '-1');
    expect(link).toHaveAttribute('aria-hidden', 'true');
    // Out of the accessibility tree entirely — not merely unlabelled, which
    // would be an unnamed link rather than no link.
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    // aria-hidden must never wrap something focusable, and tabindex=-1 is what
    // keeps that true.
    expect(
      container.querySelectorAll('[aria-hidden="true"] a[href]:not([tabindex="-1"])')
    ).toHaveLength(0);
  });
});

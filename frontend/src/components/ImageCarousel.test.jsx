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

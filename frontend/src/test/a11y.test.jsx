import { render, screen, fireEvent } from '@testing-library/react';
import { vi, describe, test, expect, beforeEach } from 'vitest';
import App from '../App';
import TooltipButton from '../components/TooltipButton';
import ImageCarousel from '../components/ImageCarousel';

// jsdom doesn't implement window.scrollTo (RouteFocusReset calls it); stub it.
window.scrollTo = vi.fn();
// App's mount effect and any redirected page hit the network — keep it inert.
globalThis.fetch = vi.fn(() =>
  Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({}) })
);

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

describe('skip link', () => {
  test('is the first tab stop and targets the main landmark', () => {
    // Authenticate so "/" renders HomePage rather than redirecting to /login:
    // a redirect is itself a route change that would (correctly) focus <main>,
    // which is not the initial-mount behaviour under test here.
    localStorage.setItem('userCode', 'TST001');
    render(<App />);

    const main = document.getElementById('main');
    expect(main).toBeTruthy();
    expect(main.getAttribute('tabindex')).toBe('-1');

    const skip = screen.getByText('Skip to content');
    expect(skip.tagName).toBe('A');
    expect(skip.getAttribute('href')).toBe('#main');

    // Tab order follows DOM order for elements with no positive tabindex, so the
    // first focusable element in the document must be the skip link.
    const focusables = document.querySelectorAll(
      'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    expect(focusables[0]).toBe(skip);

    // RouteFocusReset must NOT move focus into <main> on the initial mount, or
    // the skip link (which precedes <main>) would never be the first forward
    // Tab stop on a fresh page load.
    expect(main.contains(document.activeElement)).toBe(false);

    skip.focus();
    expect(document.activeElement).toBe(skip);
  });
});

describe('TooltipButton', () => {
  test('reveals the tooltip on keyboard focus and hides it on blur', () => {
    render(
      <TooltipButton tooltip="Need help">
        <span>icon</span>
      </TooltipButton>
    );

    // The tooltip text node is not rendered until the control is focused
    // (the button still carries it as an aria-label for assistive tech).
    expect(screen.queryByText('Need help')).toBeNull();
    expect(screen.getByRole('button', { name: 'Need help' })).toBeInTheDocument();

    const wrapper = screen.getByRole('button', { name: 'Need help' }).parentElement;
    fireEvent.focusIn(wrapper);
    expect(screen.getByText('Need help')).toBeInTheDocument();

    fireEvent.focusOut(wrapper);
    expect(screen.queryByText('Need help')).toBeNull();
  });

  // WCAG 1.4.13 "dismissible": content shown on hover/focus must be dismissible
  // without moving the pointer or the focus, or it can obscure the row beneath
  // it with no way out for a keyboard user.
  test('Escape dismisses the bubble but leaves focus on the button', () => {
    render(
      <TooltipButton tooltip="Need help">
        <span>icon</span>
      </TooltipButton>
    );

    const button = screen.getByRole('button', { name: 'Need help' });
    const wrapper = button.parentElement;
    fireEvent.focusIn(wrapper);
    button.focus();
    expect(screen.getByText('Need help')).toBeInTheDocument();

    // Dispatched on document, not the wrapper: a mouse user reading the bubble
    // usually has focus elsewhere, so that is the only listener that can serve
    // both the pointer and the keyboard case.
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByText('Need help')).toBeNull();
    // Dismissing must not cost the user their place in the table.
    expect(document.activeElement).toBe(button);

    // The dismissal is per-reveal, not permanent: focusing away and back shows
    // the label again, so Escape can't silently disable the affordance.
    fireEvent.focusOut(wrapper);
    fireEvent.focusIn(wrapper);
    expect(screen.getByText('Need help')).toBeInTheDocument();
  });

  // The bubble repeats the button's own aria-label verbatim; exposing both would
  // make a screen reader announce the label twice.
  test('the bubble is hidden from assistive tech, leaving one accessible name', () => {
    render(
      <TooltipButton tooltip="Need help">
        <span>icon</span>
      </TooltipButton>
    );

    const wrapper = screen.getByRole('button', { name: 'Need help' }).parentElement;
    fireEvent.focusIn(wrapper);
    expect(screen.getByText('Need help')).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('ImageCarousel', () => {
  test('announces the current image through a live region', () => {
    render(<ImageCarousel images={['a.jpg', 'b.jpg']} alt="My Thing" />);

    const live = document.querySelector('.image-carousel [aria-live="polite"]');
    expect(live).toBeTruthy();
    expect(live).toHaveTextContent(/image 1 of 2/i);

    fireEvent.click(screen.getByRole('button', { name: 'Next image' }));
    expect(live).toHaveTextContent(/image 2 of 2/i);
  });
});

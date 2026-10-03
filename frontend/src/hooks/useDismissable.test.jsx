import { render, screen, fireEvent } from '@testing-library/react';
import { useRef, useState } from 'react';
import { describe, test, expect, beforeEach } from 'vitest';
import useDismissable from './useDismissable';

/**
 * The dismissal contract both hero menus stand on (`AccountMenu` since
 * 2026-09-28, the collection menu since 2026-10-03). The harness is one
 * disclosure button plus a wrapper span, the exact shape the menus render —
 * the hook has no life of its own apart from that shape.
 */

function Harness() {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);
  const buttonRef = useRef(null);
  useDismissable({ open, setOpen, wrapperRef, buttonRef });
  return (
    <div>
      <button type="button" ref={buttonRef} onClick={() => setOpen((v) => !v)}>
        Trigger
      </button>
      <button type="button">Outside</button>
      <span ref={wrapperRef}>{open && <div>Panel</div>}</span>
    </div>
  );
}

beforeEach(() => {
  localStorage.clear();
});

describe('useDismissable', () => {
  test('Escape closes the open panel and returns focus to the trigger', () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Trigger' }));
    expect(screen.getByText('Panel')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByText('Panel')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Trigger' })).toHaveFocus();
  });

  test('a mousedown inside the wrapper does not close the panel', () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Trigger' }));

    fireEvent.mouseDown(screen.getByText('Panel'));

    expect(screen.getByText('Panel')).toBeInTheDocument();
  });

  test('a mousedown outside the wrapper closes the panel', () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Trigger' }));

    fireEvent.mouseDown(screen.getByRole('button', { name: 'Outside' }));

    expect(screen.queryByText('Panel')).not.toBeInTheDocument();
  });

  test('a closed panel listens to nothing: Escape leaves the focus wherever it is', () => {
    // The listeners live only while the panel is open. While closed, an
    // Escape must not reach the handler — the observable half of that is the
    // `focus()` it would fire: focus sitting elsewhere has to stay there.
    render(<Harness />);
    const outside = screen.getByRole('button', { name: 'Outside' });
    outside.focus();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(document.activeElement).toBe(outside);
    // And the component is still usable afterwards.
    fireEvent.click(screen.getByRole('button', { name: 'Trigger' }));
    expect(screen.getByText('Panel')).toBeInTheDocument();
  });
});

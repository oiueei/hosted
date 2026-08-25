import { render, screen, fireEvent } from '@testing-library/react';
import { describe, test, expect, vi } from 'vitest';
import InfoPopover from './InfoPopover';

describe('InfoPopover', () => {
  test('the (i) button starts closed with no aria-controls, then opens on click', () => {
    render(
      <InfoPopover title="CSV format" id="panel-1">
        <p>body</p>
      </InfoPopover>
    );
    const button = screen.getByRole('button', { name: 'CSV format' });
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(button).not.toHaveAttribute('aria-controls');
    expect(screen.queryByText('body')).not.toBeInTheDocument();

    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'true');
    expect(button).toHaveAttribute('aria-controls', 'panel-1');
    expect(screen.getByText('body')).toBeInTheDocument();
  });

  test('the positioning class lives on the wrapper div, never on the HDS Notification', () => {
    render(
      <InfoPopover title="CSV format" id="panel-1">
        <p>body</p>
      </InfoPopover>
    );
    fireEvent.click(screen.getByRole('button', { name: 'CSV format' }));

    // This is the BulkInviteCsv bug this component fixes: HDS's Notification
    // root carries its own `position: relative` at the same selector
    // specificity as a single custom class, so a positioning class passed as
    // `className` to Notification is not reliably absolute. The wrapper we
    // own must carry it instead.
    const wrapper = document.getElementById('panel-1');
    expect(wrapper).toHaveClass('info-popover-panel');

    const notification = wrapper.querySelector('[class*="notification"]');
    expect(notification).not.toHaveClass('info-popover-panel');
  });

  // WCAG 1.4.13 "dismissible": the panel opens on hover and on focus, so it must
  // be closable without moving the pointer or the focus. Without this, the panel
  // sits over the field below it and a keyboard user has no way out.
  test('Escape closes the panel and leaves focus on the button', () => {
    render(
      <InfoPopover title="CSV format" id="panel-1">
        <p>body</p>
      </InfoPopover>
    );

    const button = screen.getByRole('button', { name: 'CSV format' });
    fireEvent.mouseEnter(button.closest('.info-popover'));
    button.focus();
    expect(screen.getByText('body')).toBeInTheDocument();

    // Dispatched on document, not the wrapper: a mouse user reading the panel
    // usually has focus elsewhere, so that is the only listener that can serve
    // both the pointer and the keyboard case.
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByText('body')).not.toBeInTheDocument();
    // Dismissing must not cost the user their place in the form.
    expect(document.activeElement).toBe(button);
    // Closing is the dismissal, so the button's own disclosure state has to
    // agree with what is on screen — a stale aria-expanded="true" would point
    // assistive tech at a panel that is no longer there.
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(button).not.toHaveAttribute('aria-controls');
  });

  test('the dismissal is per-reveal: the panel opens again on the next hover', () => {
    render(
      <InfoPopover title="CSV format" id="panel-1">
        <p>body</p>
      </InfoPopover>
    );

    const wrapper = screen.getByRole('button', { name: 'CSV format' }).closest('.info-popover');
    fireEvent.mouseEnter(wrapper);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByText('body')).not.toBeInTheDocument();

    // Escape must not silently disable the affordance for the rest of the page's
    // life — leaving and re-entering reveals it again.
    fireEvent.mouseLeave(wrapper);
    fireEvent.mouseEnter(wrapper);
    expect(screen.getByText('body')).toBeInTheDocument();
  });

  test('other keys leave the panel open', () => {
    render(
      <InfoPopover title="CSV format" id="panel-1">
        <p>body</p>
      </InfoPopover>
    );

    fireEvent.click(screen.getByRole('button', { name: 'CSV format' }));
    // Guards the handler against being written as "any keydown closes it",
    // which would make the panel unreadable the moment anyone typed.
    fireEvent.keyDown(document, { key: 'a' });
    fireEvent.keyDown(document, { key: 'Enter' });
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(screen.getByText('body')).toBeInTheDocument();
  });

  test('the Escape listener is removed once the panel closes', () => {
    const addSpy = vi.spyOn(document, 'addEventListener');
    const removeSpy = vi.spyOn(document, 'removeEventListener');
    render(
      <InfoPopover title="CSV format" id="panel-1">
        <p>body</p>
      </InfoPopover>
    );

    const button = screen.getByRole('button', { name: 'CSV format' });
    // Nothing is listening while the panel is shut — a document-level keydown
    // handler that outlives its panel is a leak that fires for every keystroke
    // on the page.
    expect(addSpy).not.toHaveBeenCalledWith('keydown', expect.any(Function));

    fireEvent.click(button);
    const handler = addSpy.mock.calls.find(([type]) => type === 'keydown')?.[1];
    expect(handler).toBeTypeOf('function');

    fireEvent.click(button);
    expect(removeSpy).toHaveBeenCalledWith('keydown', handler);

    addSpy.mockRestore();
    removeSpy.mockRestore();
  });

  test('closes on blur', () => {
    render(
      <InfoPopover title="CSV format" id="panel-1">
        <p>body</p>
      </InfoPopover>
    );
    const button = screen.getByRole('button', { name: 'CSV format' });
    fireEvent.click(button);
    expect(screen.getByText('body')).toBeInTheDocument();

    fireEvent.blur(button.closest('.info-popover'));
    expect(screen.queryByText('body')).not.toBeInTheDocument();
  });
});

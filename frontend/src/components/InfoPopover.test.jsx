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

  // The panel of BulkAddCsv carries a link ("Download example (ZIP)"). Tabbing from the (i)
  // towards it blurs the button first; if that closed the panel, the link would be gone
  // before it could take the focus. `relatedTarget` is where the focus is going, and RTL's
  // `fireEvent.blur` reaches React as the `focusout` its `onBlur` listens to. Driving it with
  // `userEvent.tab()` instead would not prove anything: inside `act` React batches the close
  // and the reopening the link's own focus triggers, and the test passes with the bug.
  describe('focus moving inside the popover', () => {
    const renderWithLink = () => {
      render(
        <div>
          <InfoPopover title="CSV format" id="panel-1">
            <p>body</p>
            <a href="/example.zip">Download example</a>
          </InfoPopover>
          <button type="button">elsewhere</button>
        </div>
      );
      const button = screen.getByRole('button', { name: 'CSV format' });
      fireEvent.click(button);
      return { button, link: screen.getByRole('link', { name: 'Download example' }) };
    };

    test('from the (i) button to a link in the panel keeps the panel open', () => {
      const { button, link } = renderWithLink();

      fireEvent.blur(button, { relatedTarget: link });

      expect(screen.getByText('body')).toBeInTheDocument();
      expect(link).toBeInTheDocument();
      expect(button).toHaveAttribute('aria-expanded', 'true');
    });

    test('and back from the link to the button keeps it open too', () => {
      const { button, link } = renderWithLink();

      fireEvent.blur(link, { relatedTarget: button });

      expect(screen.getByText('body')).toBeInTheDocument();
    });

    test('leaving from the button for somewhere else closes it', () => {
      const { button } = renderWithLink();

      fireEvent.blur(button, { relatedTarget: screen.getByRole('button', { name: 'elsewhere' }) });

      expect(screen.queryByText('body')).not.toBeInTheDocument();
    });

    test('leaving from the link — the last stop inside — closes it', () => {
      const { link } = renderWithLink();

      fireEvent.blur(link, { relatedTarget: screen.getByRole('button', { name: 'elsewhere' }) });

      expect(screen.queryByText('body')).not.toBeInTheDocument();
    });

    test('focus going nowhere (the window lost it) closes it', () => {
      const { button } = renderWithLink();

      fireEvent.blur(button, { relatedTarget: null });

      expect(screen.queryByText('body')).not.toBeInTheDocument();
    });
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

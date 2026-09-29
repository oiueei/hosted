import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, test, expect, beforeEach } from 'vitest';
import AccountMenu from './AccountMenu';

expect.extend(toHaveNoViolations);

/**
 * The seven routes one click away from every hero (2026-09-28) — see the
 * component's own docstring for why this is a plain disclosure, not
 * ShareCollectionMenu's HDS-Select trick. Every scenario here mirrors a line
 * from that plan: the trigger's accessible name, aria-expanded toggling,
 * the link set and its order, Escape returning focus, a click outside
 * closing it, no session meaning no render, and an axe pass with the panel
 * open.
 */

const LINKS_IN_ORDER = [
  { name: /home/i, href: '/' },
  { name: /my profile/i, href: '/me' },
  { name: /edit profile/i, href: '/me/edit' },
  { name: /create collection/i, href: '/collections/new' },
  { name: /my requests/i, href: '/my-bookings' },
  { name: /requests to me/i, href: '/owner-bookings' },
  { name: /log out/i, href: '/logout' },
];

function renderMenu() {
  return render(
    <MemoryRouter>
      <AccountMenu />
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ABC123');
});

describe('AccountMenu — signed in', () => {
  test('following a link closes the panel, even to the page already on screen', () => {
    // MemoryRouter at '/': the Home link does not unmount the menu, so only
    // the menu itself can close its panel.
    renderMenu();
    fireEvent.click(screen.getByRole('button', { name: /your account/i }));

    fireEvent.click(screen.getByRole('link', { name: /home/i }));

    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /your account/i })).toHaveAttribute(
      'aria-expanded',
      'false'
    );
  });

  test('the trigger has an accessible name and starts collapsed', () => {
    renderMenu();

    const trigger = screen.getByRole('button', { name: /your account/i });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  test('a click opens it: aria-expanded flips and every link is there, in order', () => {
    renderMenu();

    fireEvent.click(screen.getByRole('button', { name: /your account/i }));

    expect(screen.getByRole('button', { name: /your account/i })).toHaveAttribute(
      'aria-expanded',
      'true'
    );
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(LINKS_IN_ORDER.length);
    LINKS_IN_ORDER.forEach((expected, i) => {
      expect(links[i]).toHaveAccessibleName(expected.name);
      expect(links[i]).toHaveAttribute('href', expected.href);
    });
  });

  test('a second click closes it again', () => {
    renderMenu();
    const trigger = screen.getByRole('button', { name: /your account/i });

    fireEvent.click(trigger);
    fireEvent.click(trigger);

    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  test('Escape closes it and returns focus to the trigger', () => {
    renderMenu();
    const trigger = screen.getByRole('button', { name: /your account/i });
    fireEvent.click(trigger);
    expect(screen.getAllByRole('link').length).toBeGreaterThan(0);

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  test('a click outside the menu closes it, without moving focus anywhere in particular', () => {
    render(
      <MemoryRouter>
        <button type="button">Outside</button>
        <AccountMenu />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole('button', { name: /your account/i }));
    expect(screen.getAllByRole('link').length).toBeGreaterThan(0);

    fireEvent.mouseDown(screen.getByRole('button', { name: 'Outside' }));

    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /your account/i })).toHaveAttribute(
      'aria-expanded',
      'false'
    );
  });

  test('a click inside the open panel is not mistaken for a click outside', () => {
    renderMenu();
    fireEvent.click(screen.getByRole('button', { name: /your account/i }));

    fireEvent.mouseDown(screen.getByRole('link', { name: /my profile/i }));

    // Still open: the panel itself is "inside", so this must not have closed it.
    expect(screen.getAllByRole('link').length).toBeGreaterThan(0);
  });

  test('the open panel has no axe violations', async () => {
    const { container } = renderMenu();
    fireEvent.click(screen.getByRole('button', { name: /your account/i }));

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

describe('AccountMenu — signed out', () => {
  test('renders nothing at all', () => {
    localStorage.removeItem('userCode');

    const { container } = renderMenu();

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole('button', { name: /your account/i })).not.toBeInTheDocument();
  });
});

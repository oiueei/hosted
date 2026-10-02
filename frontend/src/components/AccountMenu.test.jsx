import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, test, expect, beforeEach, vi } from 'vitest';

vi.mock('../services/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '../services/api';
import AccountMenu from './AccountMenu';

expect.extend(toHaveNoViolations);

/**
 * The routes one click away from every hero (2026-09-28) — see the
 * component's own docstring for why this is a plain disclosure, not
 * ShareCollectionMenu's HDS-Select trick. Every scenario here mirrors a line
 * from that plan: the trigger's accessible name, aria-expanded toggling,
 * the link set and its order, Escape returning focus, a click outside
 * closing it, no session meaning no render, and an axe pass with the panel
 * open.
 *
 * Since 2026-10-02 the menu is Home, My profile, My requests, "Requests to me" —
 * only for an account that can receive requests, which the server says — and Log
 * out. "Edit profile" is reached from My profile and "Create collection" from Home.
 */

const ALWAYS = [
  { name: /home/i, href: '/' },
  { name: /my profile/i, href: '/me' },
  { name: /my requests/i, href: '/my-bookings' },
];
const REQUESTS_TO_ME = { name: /requests to me/i, href: '/owner-bookings' };
const LOG_OUT = { name: /log out/i, href: '/logout' };

// What GET /auth/me/ answers, as far as the menu reads it.
const meSays = (receivesRequests) =>
  apiFetch.mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ code: 'ABC123', receives_requests: receivesRequests }),
  });

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
  vi.clearAllMocks();
  meSays(false);
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

  const expectLinks = (expectedLinks) => {
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(expectedLinks.length);
    expectedLinks.forEach((expected, i) => {
      expect(links[i]).toHaveAccessibleName(expected.name);
      expect(links[i]).toHaveAttribute('href', expected.href);
    });
  };

  test('a click opens it: aria-expanded flips and the account’s links are there, in order', async () => {
    renderMenu();

    fireEvent.click(screen.getByRole('button', { name: /your account/i }));

    expect(screen.getByRole('button', { name: /your account/i })).toHaveAttribute(
      'aria-expanded',
      'true'
    );
    // An account that cannot receive requests: four links, and no Edit profile or
    // Create collection (the first is under My profile, the second on Home).
    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expectLinks([...ALWAYS, LOG_OUT]);
    expect(screen.queryByRole('link', { name: /edit profile/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /create collection/i })).toBeNull();
  });

  test('an account that can receive requests also gets "Requests to me", after My requests', async () => {
    meSays(true);
    renderMenu();

    fireEvent.click(screen.getByRole('button', { name: /your account/i }));

    await screen.findByRole('link', { name: /requests to me/i });
    expectLinks([...ALWAYS, REQUESTS_TO_ME, LOG_OUT]);
  });

  test('it asks the server when it opens, not before, and again each time', async () => {
    renderMenu();
    expect(apiFetch).not.toHaveBeenCalled();
    const trigger = screen.getByRole('button', { name: /your account/i });

    fireEvent.click(trigger);
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/auth/me/', expect.anything());
    fireEvent.click(trigger);
    fireEvent.click(trigger);

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(2));
  });

  test('if the answer cannot be had the link is left out rather than guessed', async () => {
    apiFetch.mockRejectedValue(new TypeError('Failed to fetch'));
    renderMenu();

    fireEvent.click(screen.getByRole('button', { name: /your account/i }));

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expectLinks([...ALWAYS, LOG_OUT]);
  });

  test('an error status is no answer either', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 500, json: () => Promise.resolve({}) });
    renderMenu();

    fireEvent.click(screen.getByRole('button', { name: /your account/i }));

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expectLinks([...ALWAYS, LOG_OUT]);
  });

  test('it writes nothing to the browser: the /legal names every key the app stores', async () => {
    meSays(true);
    const wroteLocal = vi.spyOn(localStorage, 'setItem');
    const wroteSession = vi.spyOn(Storage.prototype, 'setItem');
    renderMenu();

    fireEvent.click(screen.getByRole('button', { name: /your account/i }));

    await screen.findByRole('link', { name: /requests to me/i });
    expect(wroteLocal).not.toHaveBeenCalled();
    expect(wroteSession).not.toHaveBeenCalled();
    wroteLocal.mockRestore();
    wroteSession.mockRestore();
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

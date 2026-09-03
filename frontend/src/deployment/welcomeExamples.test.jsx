import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import './testI18n';
import WelcomePage from './pages/WelcomePage';

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

const setInvited = (codes) => {
  apiFetch.mockImplementation((url) => {
    if (url.startsWith('/api/v1/invited-collections/')) return ok(codes.map((code) => ({ code })));
    if (url.startsWith('/api/v1/auth/me/')) return ok({ code: 'ABC123', name: 'Lala' });
    return ok([]);
  });
};

const renderWelcome = () =>
  render(
    <MemoryRouter>
      <WelcomePage />
    </MemoryRouter>
  );

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

/**
 * The intro promises example collections; the persona links under it are
 * filtered against the three seeded demo codes. The two must agree.
 *
 * The bug: the promise switched on `accessibleCodes.size`, so an ordinary
 * invited member — who has real collections and none of the demo ones — read
 * "we've shared a few example collections with you" above five stories with
 * nothing to click.
 */
describe('WelcomePage example collections', () => {
  test('a member of only real collections is not promised examples', async () => {
    setInvited(['REAL01', 'REAL02']);
    renderWelcome();

    expect(await screen.findByText(/these stories show the kinds of things/i)).toBeInTheDocument();
    expect(screen.queryByText(/we've shared a few example collections/i)).not.toBeInTheDocument();
    // And nothing claims a link that isn't rendered.
    expect(screen.queryByRole('link', { name: /Lili's Lending Library/i })).not.toBeInTheDocument();
  });

  test('a pop-in visitor in the demo collections is promised them, and gets the links', async () => {
    setInvited(['La1aC1', 'l1l1C1', 'l0l0C1']);
    renderWelcome();

    expect(await screen.findByText(/we've shared a few example collections/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Lili's Lending Library/i })).toHaveAttribute(
      'href',
      '/collections/l1l1C1'
    );
  });

  test('a visitor with one demo collection still gets the promise and that one link', async () => {
    setInvited(['REAL01', 'l0l0C1']);
    renderWelcome();

    expect(await screen.findByText(/we've shared a few example collections/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Lolo's Leafy Lounge/i })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Lili's Lending Library/i })).not.toBeInTheDocument();
  });

  test('an unseeded deployment shows the stories without promising anything', async () => {
    setInvited([]);
    renderWelcome();

    expect(await screen.findByText(/these stories show the kinds of things/i)).toBeInTheDocument();
  });

  /**
   * Lele and Lulu owned no collection until the 2026-08 seed round gave them a
   * COMMUNITY group each, and the page went on telling their story with nothing
   * to click — the persona map still said they had none. Pinning all five keeps
   * the next persona that gains a group from going quietly linkless.
   */
  test('every persona links to their own group when the visitor can reach it', async () => {
    setInvited(['La1aC1', 'L3L3C1', 'l1l1C1', 'l0l0C1', '1u1uC1']);
    renderWelcome();

    expect(await screen.findByText(/we've shared a few example collections/i)).toBeInTheDocument();

    // One per persona, in the order they are told. The two at the ends are the
    // ones that used to be missing.
    const expected = [
      [/The Sunday swap-meet/i, '/collections/L3L3C1'],
      [/Lulu's shared workshop/i, '/collections/1u1uC1'],
      [/Lala's sabbatical sale/i, '/collections/La1aC1'],
      [/Lili's Lending Library/i, '/collections/l1l1C1'],
      [/Lolo's Leafy Lounge/i, '/collections/l0l0C1'],
    ];
    for (const [name, href] of expected) {
      expect(screen.getByRole('link', { name })).toHaveAttribute('href', href);
    }
  });

  test('the two private community groups show no link to a non-member', async () => {
    setInvited(['l1l1C1']);
    renderWelcome();

    expect(await screen.findByText(/we've shared a few example collections/i)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /The Sunday swap-meet/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Lulu's shared workshop/i })).not.toBeInTheDocument();
  });
});

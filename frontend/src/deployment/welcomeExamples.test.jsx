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

// The kind the seed gives each demo collection (core/management/commands/seed_data/common.py);
// anything else is a real group, a stall here.
const SEEDED_KINDS = {
  La1aC1: 'STALL',
  l0l0C1: 'STALL',
  L3L3C1: 'STALL',
  l1l1C1: 'LIBRARY',
  '1u1uC1': 'LIBRARY',
};

// `kinds` overrides the seeded kind of a code, to serve one the page must follow.
const setInvited = (codes, kinds = {}) => {
  apiFetch.mockImplementation((url) => {
    if (url.startsWith('/api/v1/invited-collections/'))
      return ok(
        codes.map((code) => ({ code, kind: kinds[code] || SEEDED_KINDS[code] || 'STALL' }))
      );
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
      '/library/l1l1C1'
    );
  });

  test('a link follows the kind the server serves, not a fixed one', async () => {
    setInvited(['l1l1C1'], { l1l1C1: 'SHED' });
    renderWelcome();

    expect(await screen.findByRole('link', { name: /Lili's Lending Library/i })).toHaveAttribute(
      'href',
      '/shed/l1l1C1'
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
   * Lele and Lulu each own a COMMUNITY group in the seed. The persona map once
   * said they had none, and the page told their story with nothing to click.
   * Pinning all five keeps
   * the next persona that gains a group from going quietly linkless.
   */
  test('every persona links to their own group when the visitor can reach it', async () => {
    setInvited(['La1aC1', 'L3L3C1', 'l1l1C1', 'l0l0C1', '1u1uC1']);
    renderWelcome();

    expect(await screen.findByText(/we've shared a few example collections/i)).toBeInTheDocument();

    // One per persona, in the order they are told. The two at the ends are the
    // ones that used to be missing.
    const expected = [
      [/The Sunday swap-meet/i, '/stall/L3L3C1'],
      [/Lulu's shared workshop/i, '/library/1u1uC1'],
      [/Lala's sabbatical sale/i, '/stall/La1aC1'],
      [/Lili's Lending Library/i, '/library/l1l1C1'],
      [/Lolo's Leafy Lounge/i, '/stall/l0l0C1'],
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

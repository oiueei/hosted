import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';
import { mockMatchMedia, PHONE, REDUCED_MOTION } from './matchMedia';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import CollectionPage from '../pages/CollectionPage';

/**
 * After "Add thing", on a phone: the hero fills the screen and
 * nothing of the upload is in sight, which reads as if nothing happened. So the
 * collection page — handed the new thing's code in the navigation state — says it
 * worked, brings the page down to the card if it is not already in view, puts the
 * focus on its link and marks it for a moment. On a desktop it does none of it:
 * the new card is the first of the grid and in plain sight. jsdom has no layout,
 * so the stubs below stand in for the three things it lacks: `matchMedia`,
 * `scrollIntoView` and where a card is on the screen.
 */
const thing = (over) => ({
  type: 'GIFT_THING',
  status: 'ACTIVE',
  owner: 'ABC123',
  owner_name: 'Me',
  tags: [],
  gallery_urls: [],
  ...over,
});

const COLLECTION = {
  code: 'COL001',
  headline: 'Kitchen Collection',
  description: 'Things from the kitchen',
  status: 'ACTIVE',
  visibility: 'PRIVATE',
  mode: 'PROPRIETARY',
  owner: 'ABC123',
  owner_name: 'Me',
  is_curator: true,
  is_member: false,
  co_owners: [],
  thumbnail_url: '',
  tags: [],
  // Newest first on the page: the one just uploaded is the first card.
  things: [
    thing({ code: 'NEW123', headline: 'Blue chair', created: '2026-10-04T10:00:00Z' }),
    thing({ code: 'OLD001', headline: 'Old kettle', created: '2026-07-01T10:00:00Z' }),
  ],
  invites: [],
  is_paused: false,
  allowed_thing_types: [],
  digest_frequency: 'NONE',
  allow_member_proposals: false,
};

/** Shows the router state, so a test can see it cleared. */
function StateProbe() {
  const { state } = useLocation();
  return <output data-testid="state">{JSON.stringify(state)}</output>;
}

function renderArriving(state = { addedThing: 'NEW123' }, collection = COLLECTION) {
  apiFetch.mockImplementation((url) =>
    url.startsWith('/api/v1/inbox/')
      ? Promise.resolve({ ok: true, status: 200, json: async () => [] })
      : Promise.resolve({ ok: true, status: 200, json: async () => collection })
  );
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/collections/COL001', state }]}>
      <StateProbe />
      <Routes>
        <Route path="/collections/:code" element={<CollectionPage />} />
      </Routes>
    </MemoryRouter>
  );
}

const cardOf = (code) => document.querySelector(`[data-thing-code="${code}"]`);
const uploadedNotice = () => screen.queryByText('Thing uploaded!');

// The page's effect runs after the commit that paints the cards, and the notice is
// painted in that same commit: under load `findByText` can return in between, with
// the notice on screen and nothing of what the effect does yet — the focus still on
// <body>, and a "was not called" that holds only because nothing has run. The
// effect's first act is to clear the state it was opened with and it does all the
// rest in the same pass, so the cleared state is the sign it has finished.
const effectHasRun = () =>
  waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('null'));

let media;
let scrollIntoView;
let cardRect;

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ABC123');
  vi.clearAllMocks();
  scrollIntoView = vi.fn();
  Element.prototype.scrollIntoView = scrollIntoView;
  // Below the fold unless a test says otherwise (the screen is 768px tall).
  cardRect = { top: 2000, bottom: 2300 };
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function () {
    return this.hasAttribute?.('data-thing-code')
      ? cardRect
      : { top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0 };
  });
  media = mockMatchMedia({ [PHONE]: true });
});

afterEach(() => {
  media.restore();
  delete Element.prototype.scrollIntoView;
  vi.restoreAllMocks();
});

describe('CollectionPage after adding a thing, on a phone', () => {
  test('says it worked, in a green notice', async () => {
    renderArriving();

    expect(await screen.findByText('Thing uploaded!')).toBeInTheDocument();
    // Not left running: a test that ends before the effect has run lets it fire in the next one.
    await effectHasRun();
  });

  test('brings the page down to the new card, centred and smooth, when it is out of sight', async () => {
    renderArriving();
    await screen.findByText('Thing uploaded!');
    await effectHasRun();

    expect(scrollIntoView).toHaveBeenCalledTimes(1);
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'center', behavior: 'smooth' });
    // On the new card, not on another one.
    expect(scrollIntoView.mock.contexts[0]).toBe(cardOf('NEW123'));
  });

  test('does not scroll when the card is already in view, but still says it worked', async () => {
    cardRect = { top: 120, bottom: 420 };
    renderArriving();

    expect(await screen.findByText('Thing uploaded!')).toBeInTheDocument();
    await effectHasRun();
    expect(scrollIntoView).not.toHaveBeenCalled();
    // …and still hands over the focus.
    expect(within(cardOf('NEW123')).getByRole('link', { name: 'Blue chair' })).toHaveFocus();
  });

  test('jumps instead of gliding for someone who asked for less motion', async () => {
    media.restore();
    media = mockMatchMedia({ [PHONE]: true, [REDUCED_MOTION]: true });
    renderArriving();
    await screen.findByText('Thing uploaded!');
    await effectHasRun();

    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'center', behavior: 'auto' });
  });

  test('puts the focus on the new card’s link', async () => {
    renderArriving();
    await screen.findByText('Thing uploaded!');
    await effectHasRun();

    expect(within(cardOf('NEW123')).getByRole('link', { name: 'Blue chair' })).toHaveFocus();
    expect(document.activeElement).not.toBe(
      within(cardOf('OLD001')).getByRole('link', { name: 'Old kettle' })
    );
  });

  test('marks the card in the theeeme’s colour, for about two seconds', async () => {
    localStorage.setItem(
      'theeemeColors',
      JSON.stringify({
        color_01: 'copper',
        color_02: 'suomenlinna-light',
        color_03: 'copper',
        color_04: 'black',
        color_05: 'white',
        color_06: 'white',
      })
    );
    renderArriving();
    await screen.findByText('Thing uploaded!');
    await effectHasRun();

    const card = cardOf('NEW123');
    expect(card).toHaveClass('thing-card--just-added');
    expect(card.style.getPropertyValue('--just-added-color')).toBe('var(--color-copper)');
    expect(cardOf('OLD001')).not.toHaveClass('thing-card--just-added');

    await waitFor(() => expect(card).not.toHaveClass('thing-card--just-added'), {
      timeout: 4000,
    });
  });

  test('clears the state, so a reload or the back button never repeats it', async () => {
    renderArriving();
    await screen.findByText('Thing uploaded!');

    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('null'));
  });

  test('a thing that is not on the page gets the notice alone', async () => {
    renderArriving({ addedThing: 'GONE99' });

    expect(await screen.findByText('Thing uploaded!')).toBeInTheDocument();
    await effectHasRun();
    expect(scrollIntoView).not.toHaveBeenCalled();
    expect(document.querySelector('.thing-card--just-added')).toBeNull();
  });

  test('arriving with no state does nothing at all', async () => {
    renderArriving(null);
    await screen.findByText('Blue chair');
    // No state, so nothing to clear: the title is set by the effect declared right after
    // the one under test, in the same flush, so it is the sign that one has had its turn.
    await waitFor(() => expect(document.title).toContain('Kitchen Collection'));

    expect(uploadedNotice()).toBeNull();
    expect(scrollIntoView).not.toHaveBeenCalled();
    expect(document.querySelector('.thing-card--just-added')).toBeNull();
  });
});

describe('CollectionPage after adding a thing, on a desktop', () => {
  beforeEach(() => {
    media.restore();
    media = mockMatchMedia({ [PHONE]: false });
  });

  test('says nothing, scrolls nowhere and moves no focus', async () => {
    renderArriving();
    await screen.findByText('Blue chair');
    // The state is cleared either way, which is also the sign the page has looked.
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('null'));

    expect(uploadedNotice()).toBeNull();
    expect(scrollIntoView).not.toHaveBeenCalled();
    expect(document.querySelector('.thing-card--just-added')).toBeNull();
    expect(within(cardOf('NEW123')).getByRole('link', { name: 'Blue chair' })).not.toHaveFocus();
  });
});

import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';
import en from '../i18n/locales/en.json';
import es from '../i18n/locales/es.json';
import ca from '../i18n/locales/ca.json';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import CollectionPage from '../pages/CollectionPage';

/**
 * "Your collection is taking shape. Now invite your circle →" was a quiet line under
 * the curator's hero row, shown while the group had things and nobody invited. It is
 * a third button of the row now (X6, CA 2026-10-04): `[Edit collection]` primary,
 * `[Add thing]`, `[Invite your people]`, to the invitations page — the same condition,
 * and one primary still.
 */
const THING = (over) => ({
  code: 'THG001',
  headline: 'Kettle',
  type: 'GIFT_THING',
  status: 'ACTIVE',
  owner: 'ABC123',
  owner_name: 'Me',
  created: '2026-07-01T10:00:00Z',
  tags: [],
  gallery_urls: [],
  ...over,
});

const FOUNDER = {
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
  things: [THING()],
  invites: [],
  is_paused: false,
  allowed_thing_types: [],
  digest_frequency: 'NONE',
  allow_member_proposals: false,
};

function renderCollection(collection, { signedIn = true } = {}) {
  localStorage.clear();
  if (signedIn) localStorage.setItem('userCode', 'ABC123');
  apiFetch.mockImplementation((url) =>
    url.startsWith('/api/v1/inbox/')
      ? Promise.resolve({ ok: true, status: 200, json: async () => [] })
      : Promise.resolve({ ok: true, status: 200, json: async () => collection })
  );
  return render(
    <MemoryRouter initialEntries={['/collections/COL001']}>
      <Routes>
        <Route path="/collections/:code" element={<CollectionPage />} />
      </Routes>
    </MemoryRouter>
  );
}

// The hero's row of buttons, in document order.
const heroRow = (container) => [...container.querySelectorAll('.form-hero .button-row-wide > a')];
const labels = (row) => row.map((a) => a.textContent);
const isPrimary = (link) =>
  link.style.getPropertyValue('--background-color') !== 'var(--color-white)';

beforeEach(() => vi.clearAllMocks());

describe('the curator hero row — "Invite your people"', () => {
  test('with things and nobody invited: three buttons, the third secondary, to the invitations', async () => {
    const { container } = renderCollection(FOUNDER);
    await screen.findByText('Kettle');

    const row = heroRow(container);
    expect(labels(row)).toEqual(['Edit collection', 'Add thing', 'Invite your people']);
    expect(row.map((a) => a.getAttribute('href'))).toEqual([
      '/collections/COL001/edit',
      '/collections/COL001/add',
      '/collections/COL001/invites',
    ]);
    // One primary, the first: the row keeps its rule.
    expect(row.map(isPrimary)).toEqual([true, false, false]);
  });

  test('with the first guest in, the row is the two it was', async () => {
    const { container } = renderCollection({
      ...FOUNDER,
      invites: [{ code: 'GUEST1', name: 'Lele' }],
    });
    await screen.findByText('Kettle');

    expect(labels(heroRow(container))).toEqual(['Edit collection', 'Add thing']);
    expect(screen.queryByRole('link', { name: 'Invite your people' })).toBeNull();
  });

  test('with nothing to show yet, it is not there either', async () => {
    const { container } = renderCollection({ ...FOUNDER, things: [] });
    await screen.findByRole('link', { name: 'Edit collection' });

    expect(labels(heroRow(container))).toEqual(['Edit collection', 'Add thing']);
  });

  test('a group whose things are all hidden has nothing to show: two buttons', async () => {
    const { container } = renderCollection({
      ...FOUNDER,
      things: [THING({ status: 'INACTIVE' })],
    });
    await screen.findByRole('link', { name: 'Edit collection' });

    expect(labels(heroRow(container))).toEqual(['Edit collection', 'Add thing']);
  });

  test('the line is gone: nothing says the collection is taking shape, in any wording', async () => {
    const { container } = renderCollection(FOUNDER);
    await screen.findByText('Kettle');

    expect(container.textContent).not.toMatch(/taking shape|invite your circle/i);
    // The strings left the locales, so a resurrected `t('collectionPage.inviteNudge')`
    // would print its own key — and an English-text query would pass for the wrong reason.
    expect(container.textContent).not.toMatch(/inviteNudge/);
    expect(container.querySelector('.form-hero p.invite-nudge')).toBeNull();
    // Nor as a link of the old kind, under the row.
    expect(container.querySelectorAll('a[href$="/invites"]')).toHaveLength(1);
  });

  test('only whoever runs the group has it: a member never does', async () => {
    renderCollection({ ...FOUNDER, owner: 'OTHER1', is_curator: false, is_member: true });
    await screen.findByText('Kettle');

    expect(screen.queryByRole('link', { name: 'Invite your people' })).toBeNull();
  });

  test('nor a reader with no session', async () => {
    renderCollection({ ...FOUNDER, visibility: 'PUBLIC', is_curator: false }, { signedIn: false });
    await screen.findByText('Kettle');

    expect(screen.queryByRole('link', { name: 'Invite your people' })).toBeNull();
  });
});

describe('the words of the button', () => {
  test.each([
    ['en', en, 'Invite your people'],
    ['es', es, 'Invita a tu gente'],
    ['ca', ca, 'Convida la teva gent'],
  ])('%s says "%s", and the two old keys are gone', (_lang, locale, words) => {
    expect(locale.collectionPage.inviteYourPeople).toBe(words);
    expect(locale.collectionPage).not.toHaveProperty('inviteNudge');
    expect(locale.collectionPage).not.toHaveProperty('inviteNudgeLink');
  });
});

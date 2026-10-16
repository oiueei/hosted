import { render, screen, waitFor } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { MemoryRouter, Routes, Route } from 'react-router';
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: () => 'tok',
  extractApiError: () => null,
}));

import { apiFetch } from '../services/api';
import LeaveCollectionPage from '../pages/LeaveCollectionPage';
import RemoveGuestPage from '../pages/RemoveGuestPage';
import { settle } from './settle';

expect.extend(toHaveNoViolations);

// A member who goes takes their things in that group with them, and the two pages
// that end a membership say which ones before the person decides. The collection
// is the JSON `CollectionSerializer` emits (a member is served their own INACTIVE
// things too, which is why one of the three below is INACTIVE).
const thing = (code, owner, headline, status = 'ACTIVE') => ({ code, owner, headline, status });

const COLLECTION = (things) => ({
  code: 'COL001',
  headline: 'Kitchen Collection',
  owner: 'FOUND1',
  is_curator: false,
  things,
});

const answer = (status, body) =>
  Promise.resolve({ ok: status < 400, status, json: async () => body });

const notice = () => screen.queryByRole('heading', { name: /Your things go with you/ });

describe('LeaveCollectionPage says which of the member’s things will be deleted', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('userCode', 'MEMB01');
    vi.clearAllMocks();
  });
  afterEach(() => vi.restoreAllMocks());

  const renderPage = () =>
    render(
      <MemoryRouter
        initialEntries={[
          { pathname: '/collections/COL001/leave', state: { headline: 'Kitchen Collection' } },
        ]}
      >
        <Routes>
          <Route path="/collections/:code/leave" element={<LeaveCollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

  test('with one thing it names it, in the singular', async () => {
    apiFetch.mockImplementation(() =>
      answer(200, COLLECTION([thing('T1', 'MEMB01', 'Drill'), thing('T2', 'FOUND1', 'Ladder')]))
    );
    renderPage();

    expect(
      await screen.findByText(/Leaving deletes your thing in this group: Drill\./)
    ).toBeInTheDocument();
    expect(notice()).toBeInTheDocument();
  });

  test('with several it counts them and lists them as a sentence', async () => {
    apiFetch.mockImplementation(() =>
      answer(
        200,
        COLLECTION([
          thing('T1', 'MEMB01', 'Drill'),
          thing('T2', 'MEMB01', 'Ladder', 'INACTIVE'),
          thing('T3', 'MEMB01', 'Saw'),
        ])
      )
    );
    renderPage();

    expect(
      await screen.findByText(
        /Leaving deletes your 3 things in this group: Drill, Ladder, and Saw\./
      )
    ).toBeInTheDocument();
  });

  test('a title written in several languages reads in the one on screen', async () => {
    apiFetch.mockImplementation(() =>
      answer(200, COLLECTION([thing('T1', 'MEMB01', '{"es": "Taladro", "en": "Drill"}')]))
    );
    renderPage();

    expect(await screen.findByText(/in this group: Drill\./)).toBeInTheDocument();
  });

  test('another member’s thing is not listed, and with none of their own there is no notice', async () => {
    apiFetch.mockImplementation(() =>
      answer(200, COLLECTION([thing('T2', 'FOUND1', 'Ladder'), thing('T3', 'OTHER1', 'Saw')]))
    );
    renderPage();
    await screen.findByRole('button', { name: 'Leave the group' });
    await settle(apiFetch);

    expect(notice()).not.toBeInTheDocument();
    expect(screen.queryByText(/Ladder|Saw/)).not.toBeInTheDocument();
  });

  test.each([
    ['refused', () => answer(403, {})],
    ['never arrived', () => Promise.reject(new TypeError('offline'))],
  ])(
    'if the group cannot be read (%s) the page still lets the member leave',
    async (_case, get) => {
      apiFetch.mockImplementation((url, opts) =>
        opts?.method === 'POST' ? answer(200, { things_deleted: 0 }) : get()
      );
      renderPage();
      await settle(apiFetch);

      expect(notice()).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Leave the group' })).toBeEnabled();
    }
  );

  test('the notice has no accessibility violations', async () => {
    apiFetch.mockImplementation(() =>
      answer(200, COLLECTION([thing('T1', 'MEMB01', 'Drill'), thing('T3', 'MEMB01', 'Saw')]))
    );
    const { container } = renderPage();
    await waitFor(() => expect(notice()).toBeInTheDocument());

    expect(await axe(container, { rules: { region: { enabled: false } } })).toHaveNoViolations();
  });
});

describe('RemoveGuestPage says which of their things will be deleted with the member', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('userCode', 'FOUND1');
    vi.clearAllMocks();
    apiFetch.mockImplementation(() => answer(200, {}));
  });
  afterEach(() => vi.restoreAllMocks());

  const renderPage = (state) =>
    render(
      <MemoryRouter initialEntries={[{ pathname: '/collections/COL001/invites/remove', state }]}>
        <Routes>
          <Route path="/collections/:code/invites/remove" element={<RemoveGuestPage />} />
        </Routes>
      </MemoryRouter>
    );

  const removing = { guestCode: 'GST001', guestName: 'Ana' };
  const aviso = () => screen.queryByRole('heading', { name: /Their things go with them/ });

  test('with one thing it names it, in the singular', () => {
    renderPage({ ...removing, thingTitles: ['Drill'] });

    expect(
      screen.getByText(/Removing them also deletes their thing in this group: Drill\./)
    ).toBeInTheDocument();
    expect(aviso()).toBeInTheDocument();
  });

  test('with several it counts them and lists them as a sentence', () => {
    renderPage({ ...removing, thingTitles: ['Drill', 'Ladder', '{"es": "Sierra", "en": "Saw"}'] });

    expect(
      screen.getByText(
        /Removing them also deletes their 3 things in this group: Drill, Ladder, and Saw\./
      )
    ).toBeInTheDocument();
  });

  test.each([
    ['none', []],
    ['not sent at all (a page reached by hand)', undefined],
  ])('with their things %s there is no notice', (_case, thingTitles) => {
    renderPage({ ...removing, thingTitles });

    expect(aviso()).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove' })).toBeEnabled();
  });

  test('a co-curator with things is warned the same way', () => {
    renderPage({ guestCode: 'COOW01', guestName: 'Lele', thingTitles: ['Catalogue entry'] });

    expect(screen.getByText(/their thing in this group: Catalogue entry\./)).toBeInTheDocument();
  });

  test('the notice has no accessibility violations', async () => {
    const { container } = renderPage({ ...removing, thingTitles: ['Drill', 'Saw'] });

    expect(await axe(container, { rules: { region: { enabled: false } } })).toHaveNoViolations();
  });
});

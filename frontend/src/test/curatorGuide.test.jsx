import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

// The deployment's guide for whoever runs a group, switched by the test: upstream it
// is null, a deployment that has one writes its route into `deployment/`.
const deployment = vi.hoisted(() => ({ curatorGuidePath: null }));
vi.mock('../deployment', async (orig) => ({
  ...(await orig()),
  requestAccessPaths: {},
  get curatorGuidePath() {
    return deployment.curatorGuidePath;
  },
}));

import { apiFetch } from '../services/api';
import CollectionMenu from '../components/CollectionMenu';
import InboxNotifications from '../components/InboxNotifications';
import { press } from './settle';

const PROMOTED = {
  code: 'NOT100',
  type: 'PROMOTED_CO_OWNER',
  payload: { collection_headline: 'Tools', collection_code: 'COL001', collection_kind: 'LIBRARY' },
  created: '2026-10-01T10:00:00Z',
};
const downloads = {
  active: null,
  calendar: { downloading: false, download: vi.fn() },
  stats: { downloading: false, download: vi.fn() },
  collectionExport: { downloading: false, download: vi.fn() },
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ABC123');
  deployment.curatorGuidePath = null;
  apiFetch.mockImplementation((url) =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: async () =>
        url.startsWith('/api/v1/inbox/') ? [PROMOTED] : { receives_requests: false },
    })
  );
});

const renderMenu = (isCurator = true) =>
  render(
    <MemoryRouter>
      <CollectionMenu
        code="COL001"
        kind="LIBRARY"
        headline="Tools"
        isCurator={isCurator}
        downloads={downloads}
      />
    </MemoryRouter>
  );
const renderInbox = () =>
  render(
    <MemoryRouter>
      <InboxNotifications />
    </MemoryRouter>
  );
const open = () => press(screen.getByRole('button', { name: /collection options/i }));

describe('a deployment’s guide for whoever runs a group', () => {
  test('with a route, the curator’s menu has an entry that goes to it', async () => {
    deployment.curatorGuidePath = '/guide/running-a-group';
    renderMenu();
    await open();

    expect(screen.getByRole('link', { name: 'If you run a group' })).toHaveAttribute(
      'href',
      '/guide/running-a-group'
    );
  });

  test('it sits beside the downloads, after them', async () => {
    deployment.curatorGuidePath = '/guide/running-a-group';
    renderMenu();
    await open();

    const entries = [
      ...document.querySelectorAll('.collection-menu-panel a, .collection-menu-panel button'),
    ];
    const names = entries.map((e) => e.textContent.trim());
    expect(names.indexOf('If you run a group')).toBeGreaterThan(
      names.indexOf('Download the whole collection (JSON)')
    );
  });

  test('a member’s menu does not have it', async () => {
    deployment.curatorGuidePath = '/guide/running-a-group';
    renderMenu(false);
    await open();

    expect(screen.queryByRole('link', { name: 'If you run a group' })).toBeNull();
  });

  test('with a route, the co-curator notice carries the same link', async () => {
    deployment.curatorGuidePath = '/guide/running-a-group';
    renderInbox();

    const link = await screen.findByRole('link', { name: 'If you run a group' });
    expect(link).toHaveAttribute('href', '/guide/running-a-group');
  });

  test('another kind of notice does not', async () => {
    deployment.curatorGuidePath = '/guide/running-a-group';
    apiFetch.mockImplementation(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: async () => [{ ...PROMOTED, type: 'DEMOTED_CO_OWNER' }],
      })
    );
    renderInbox();

    await screen.findByText(/Tools/);
    expect(screen.queryByRole('link', { name: 'If you run a group' })).toBeNull();
  });

  test('without a route, neither place shows anything', async () => {
    renderMenu();
    await open();
    expect(screen.queryByRole('link', { name: 'If you run a group' })).toBeNull();

    renderInbox();
    await waitFor(() => expect(screen.getAllByText(/Tools/).length).toBeGreaterThan(0));
    expect(screen.queryByRole('link', { name: 'If you run a group' })).toBeNull();
  });
});

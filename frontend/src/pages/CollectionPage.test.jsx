import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { vi, describe, test, expect, beforeEach } from 'vitest';

expect.extend(toHaveNoViolations);

// The busier hero (headline + tags + owner buttons + share menu) is what S8
// adds a photo composition to on top of — HeroPhoto itself is unit-tested
// separately (HeroPhoto.test.jsx); this checks the combination doesn't
// introduce an axe violation the way the shared smoke.test.jsx fixture
// (thumbnail_url: '') never exercises.
const COLLECTION_WITH_PHOTO = {
  code: 'COL001',
  headline: 'Kitchen Collection',
  description: 'Things from the kitchen',
  status: 'ACTIVE',
  visibility: 'PRIVATE',
  mode: 'PROPRIETARY',
  owner: 'ABC123',
  owner_name: 'Test User',
  thumbnail_url: 'https://res.cloudinary.com/demo/image/upload/oiueei/collections/cover.jpg',
  tags: [],
  things: [],
  invites: [],
  is_paused: false,
  allowed_thing_types: [],
};

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(COLLECTION_WITH_PHOTO) })
  ),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import CollectionPage from './CollectionPage';

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ABC123');
});

describe('CollectionPage with a collection thumbnail', () => {
  test('renders the photo hero with no accessibility violations', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(container.querySelector('.hero-photo-wrap')).toBeTruthy();
    });
    expect(container.querySelector('.form-hero--photo')).toBeTruthy();
    expect(container.querySelector('img.hero-photo')).toHaveAttribute(
      'src',
      COLLECTION_WITH_PHOTO.thumbnail_url
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

describe('CollectionPage anonymous visitor intro', () => {
  test('shows a join link for a signed-out visitor', async () => {
    localStorage.clear();
    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    const link = await screen.findByRole('link', { name: /join to take part/i });
    expect(link).toHaveAttribute('href', '/collections/COL001/join');
  });

  test('does not show the join link for an authenticated visitor', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(container.querySelector('.form-hero-title')).toHaveTextContent('Kitchen Collection');
    });
    expect(screen.queryByRole('link', { name: /join to take part/i })).toBeNull();
  });
});

describe('CollectionPage inactive-things grid', () => {
  // The inactive grid used to build its own inline `onUpdateThing` instead of
  // sharing the page's useCallback'd one. Both did the same work, so the bug it
  // could hide is silent: hand the wrong callback (or none) to these cards and
  // reactivating a hidden thing still POSTs and still succeeds, but the card
  // never leaves the "Inactive things" section — the owner clicks Reactivate
  // again, and again. This pins that the card's update actually reaches the
  // page's state.
  const HIDDEN_THING = {
    code: 'THG001',
    headline: 'Old blender',
    type: 'GIFT_THING',
    status: 'INACTIVE',
    owner: 'ABC123',
    owner_name: 'Test User',
    created: '2026-07-01T10:00:00Z',
    tags: [],
    gallery_urls: [],
  };
  const COLLECTION_WITH_HIDDEN = {
    ...COLLECTION_WITH_PHOTO,
    thumbnail_url: '',
    things: [HIDDEN_THING],
  };

  test('reactivating a hidden thing moves it out of the hidden section', async () => {
    const { apiFetch } = await import('../services/api');
    apiFetch.mockImplementation((url) => {
      if (url.includes('/activate/')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(COLLECTION_WITH_HIDDEN),
      });
    });

    render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );

    // It starts under "Hidden things", carrying the owner-only Inactive tag.
    await screen.findByRole('heading', { name: 'Inactive things' });
    expect(screen.getByText('Old blender')).toBeInTheDocument();
    expect(screen.getByText('Inactive')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Reactivate' }));

    // The section disappears with its last member — proof the card's patch
    // landed in the page's `things` state, not in a detached copy.
    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: 'Inactive things' })).toBeNull();
    });
    expect(screen.queryByText('Inactive')).toBeNull();
    expect(screen.getByText('Old blender')).toBeInTheDocument();
  });
});

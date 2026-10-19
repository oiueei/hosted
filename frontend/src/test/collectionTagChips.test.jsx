import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';
import { declarations } from './cssRules';

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import CollectionPage from '../pages/CollectionPage';

const COLLECTION = {
  code: 'COL001',
  headline: 'Toy library',
  description: 'Shared toys',
  status: 'ACTIVE',
  visibility: 'PRIVATE',
  mode: 'COMMUNITY',
  owner: 'ABC123',
  owner_name: 'Test User',
  thumbnail_url: '',
  tags: ['Books'],
  things: [
    { code: 'THG001', headline: 'Cot', type: 'GIFT_THING', status: 'ACTIVE', tags: ['Books'] },
  ],
  invites: [],
  is_paused: false,
  allowed_thing_types: [],
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ABC123');
  apiFetch.mockImplementation(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(COLLECTION) })
  );
});

/**
 * The filter chips are 48px tall pills with 16px Medium text and 20px at the sides;
 * a margin G stands between the koro and the bar and between the bar and the cards.
 * jsdom paints nothing: the stylesheet is read for the measures, the DOM for what
 * the margin above the bar is made of.
 */
describe('the tag filter chips', () => {
  test('are 48px tall, 16px Medium, 20px at the sides, with a 24px radius', () => {
    expect(declarations('.tag-chip', 'height')).toEqual(['48px']);
    expect(declarations('.tag-chip', 'min-height')).toEqual([]);
    expect(declarations('.tag-chip', 'font-size')).toEqual(['var(--fontsize-body-m)']);
    expect(declarations('.tag-chip', 'font-weight')).toEqual(['500']);
    expect(declarations('.tag-chip', 'padding')).toEqual(['0 20px']);
    expect(declarations('.tag-chip', 'border-radius')).toEqual(['24px']);
  });

  test('keep their colours, their 8px gap and a single scrolling line', () => {
    expect(declarations('.tag-chip', 'background-color')).toEqual(['var(--color-bus-light)']);
    expect(declarations('.tag-chip', 'color')).toEqual(['var(--color-bus)']);
    expect(declarations(".tag-chip[aria-pressed='true']", 'background-color')).toEqual([
      'var(--color-bus)',
    ]);
    expect(declarations('.tag-filter-bar', 'gap')).toEqual(['var(--spacing-2-xs)']);
    expect(declarations('.tag-filter-bar', 'overflow-x')).toEqual(['auto']);
    expect(declarations('.tag-chip', 'white-space')).toEqual(['nowrap']);
  });

  test('stand G under the bar, the focus-ring room it keeps coming off that margin', () => {
    expect(declarations('.tag-filter-bar', 'margin-bottom')).toEqual([
      'calc(var(--page-margin) - var(--spacing-3-xs))',
    ]);
    expect(declarations('.tag-filter-bar', 'padding-bottom')).toEqual(['var(--spacing-3-xs)']);
  });

  test('have no spacer above them: the page’s own margin is the G under the koro', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/collections/COL001']}>
        <Routes>
          <Route path="/collections/:code" element={<CollectionPage />} />
        </Routes>
      </MemoryRouter>
    );
    await screen.findByRole('button', { name: /Books/ });
    const bar = container.querySelector('.tag-filter-bar');

    expect(bar.previousElementSibling.tagName).toBe('H2');
    expect(bar.previousElementSibling).toHaveClass('sr-only');
    expect(declarations('.page-container', 'padding')).toEqual(['var(--page-margin)']);
  });
});

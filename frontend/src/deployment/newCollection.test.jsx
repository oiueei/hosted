import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

import './testI18n';
import NewCollectionPage from '../pages/NewCollectionPage';
import { requestAccessPaths, externalForms } from './index';
import { settle } from '../test/settle';

/**
 * `/new`, for an account this deployment has not yet validated.
 *
 * What it protects: the kinds the policy withholds (a library, a shed) keep their cards,
 * and the "Request access" button on each one leads to the page of the app that explains
 * that kind — in the same tab — and not to the form hosted elsewhere. The real
 * `deployment/` module is used, so this also pins the values `requestAccessPaths` has here.
 */

window.scrollTo = vi.fn();

// What the creator policy answers an unvalidated account on `GET /auth/me/`.
const UNVALIDATED = {
  collection_modes: ['PROPRIETARY'],
  collection_kinds: ['STALL'],
  thing_types: ['GIFT_THING', 'SELL_THING'],
  request_url: 'https://tally.so/r/zxaY4M',
  co_owners_enabled: true,
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', `U${Math.random()}`);
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ capabilities: UNVALIDATED }),
    })
  );
});

const renderNew = async () => {
  render(
    <MemoryRouter initialEntries={['/new']}>
      <Routes>
        <Route path="/new" element={<NewCollectionPage />} />
      </Routes>
    </MemoryRouter>
  );
  await settle(fetch);
  return screen.getAllByRole('listitem');
};

describe('the kind chooser of an account that has not been validated', () => {
  test('the stall has its button, the library and the shed each a request to their own page', async () => {
    const [stall, library, shed] = await renderNew();

    expect(within(stall).getByRole('link')).toHaveAttribute('href', '/stall/new');
    const toLibrary = within(library).getByRole('link', { name: 'Request access' });
    expect(toLibrary).toHaveAttribute('href', '/access/library');
    const toShed = within(shed).getByRole('link', { name: 'Request access' });
    expect(toShed).toHaveAttribute('href', '/access/shed');
  });

  test('both open in the same tab, with no new-tab announcement', async () => {
    const [, library, shed] = await renderNew();

    for (const card of [library, shed]) {
      const link = within(card).getByRole('link', { name: 'Request access' });
      expect(link).not.toHaveAttribute('target');
      expect(link).toHaveAccessibleName('Request access');
    }
  });

  test('the form hosted elsewhere is not what the button opens, though this deployment has one', async () => {
    const [, library] = await renderNew();

    expect(externalForms.requestAccess.es).toMatch(/^https:/);
    const link = within(library).getByRole('link', { name: 'Request access' });
    expect(link.getAttribute('href')).not.toMatch(/^https?:/);
  });

  test('the two paths are the two pages the deployment has', () => {
    expect(requestAccessPaths).toEqual({ LIBRARY: '/access/library', SHED: '/access/shed' });
  });
});

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

window.scrollTo = vi.fn();

const navigate = vi.fn();
vi.mock('react-router', async () => ({
  ...(await vi.importActual('react-router')),
  useNavigate: () => navigate,
}));

// The real `extractApiError`: the refusal tests feed it real response bodies and
// check what it makes of them reaches the toast.
vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal()),
  apiFetch: vi.fn(),
  getCsrfToken: () => 'tok',
}));

import { apiFetch } from '../services/api';
import AddThingPage from './AddThingPage';
import en from '../i18n/locales/en.json';
import { settle } from '../test/settle';

// The form a member meets first in a COMMUNITY collection. There is no choice of
// verb in it: the collection's kind and the price decide it, the server puts it, and
// the form sends none. What it still has to honour is the collection's own list — a
// group whose members may not set a price has no price field — and the deployment's
// policy, asked about the verb the price makes.

const collection = (over = {}) => ({
  code: 'COL001',
  headline: 'The lending library',
  kind: 'STALL',
  allowed_thing_types: ['GIFT_THING', 'SELL_THING'],
  tags: [],
  ...over,
});

function mockApi({ coll = collection(), post = { ok: true, body: {} } } = {}) {
  apiFetch.mockImplementation((url, opts) => {
    if (opts?.method === 'POST') {
      return Promise.resolve({
        ok: post.ok,
        status: post.status ?? (post.ok ? 201 : 400),
        json: async () => post.body,
      });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => coll });
  });
}

// The page asks the collection and the deployment's capabilities as it mounts: the
// helper hands the view back once both have answered.
const renderPage = async () => {
  const view = render(
    <MemoryRouter initialEntries={['/collections/COL001/add']}>
      <Routes>
        <Route path="/collections/:code/add" element={<AddThingPage />} />
      </Routes>
    </MemoryRouter>
  );
  await settle(apiFetch);
  return view;
};

const postBody = () => {
  const call = apiFetch.mock.calls.find(([, o]) => o?.method === 'POST');
  return call && JSON.parse(call[1].body);
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'USR001');
  vi.clearAllMocks();
});
afterEach(() => vi.restoreAllMocks());

/**
 * The CSV import left this page: it is `/collections/:code/import`
 * now, reached from a curator's collection menu. This one is the form for one thing.
 */
describe('AddThingPage — no CSV import any more', () => {
  test('the page has no bulk section and no import heading', async () => {
    mockApi();
    const { container } = await renderPage();
    await screen.findByLabelText(/Title/);

    expect(container.querySelector('#bulk-add, .bulk-add-section')).toBeNull();
    expect(screen.queryByText(/Add multiple things from a CSV/)).toBeNull();
    expect(screen.queryByText(/Add many at once|Add several at once/)).toBeNull();
  });

  test('the old #bulk-add address scrolls nowhere: there is nothing to scroll to', async () => {
    mockApi();
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    try {
      render(
        <MemoryRouter initialEntries={['/collections/COL001/add#bulk-add']}>
          <Routes>
            <Route path="/collections/:code/add" element={<AddThingPage />} />
          </Routes>
        </MemoryRouter>
      );
      await screen.findByLabelText(/Title/);
      await settle(apiFetch);

      expect(scrollIntoView).not.toHaveBeenCalled();
    } finally {
      delete Element.prototype.scrollIntoView;
    }
  });
});

describe('AddThingPage — the price decides the verb, the server puts it', () => {
  test('a gift and a sale are the same form: a price, or none', async () => {
    mockApi();
    await renderPage();

    const price = await screen.findByLabelText(/Price/);
    expect(price).toBeInTheDocument();
    // Typing a price changes nothing else on the form.
    const before = screen.getAllByRole('textbox').length;
    fireEvent.change(price, { target: { value: '5' } });
    expect(screen.getAllByRole('textbox').length).toBe(before);
    expect(screen.getByText('Availability')).toBeInTheDocument();
  });

  test('no verb is sent, with a price or without one', async () => {
    mockApi();
    await renderPage();
    fireEvent.change(await screen.findByLabelText(/Title/), { target: { value: 'Old bike' } });
    fireEvent.change(screen.getByLabelText(/Price/), { target: { value: '30' } });

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(postBody()).toBeTruthy());
    expect(postBody()).toMatchObject({
      headline: 'Old bike',
      fee: '30',
      collection_code: 'COL001',
    });
    expect(postBody()).not.toHaveProperty('type');
  });

  test('a price is optional: with none the thing is sent without a fee', async () => {
    mockApi();
    await renderPage();
    fireEvent.change(await screen.findByLabelText(/Title/), { target: { value: 'Blue armchair' } });

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(postBody()).toBeTruthy());
    expect(postBody()).not.toHaveProperty('fee');
    expect(screen.queryByText(/Price is required/)).toBeNull();
  });

  test.each([
    ['STALL', 'Price (optional)'],
    ['LIBRARY', 'Rental price (optional)'],
  ])('a %s asks for its price in its own words', async (kind, label) => {
    mockApi({ coll: collection({ kind }) });
    await renderPage();

    expect(
      await screen.findByLabelText(new RegExp(label.replace(/[()]/g, '\\$&')))
    ).toBeInTheDocument();
  });

  test('a community group whose members may not set a price has no price field', async () => {
    mockApi({
      coll: collection({
        mode: 'COMMUNITY',
        is_member: true,
        allowed_thing_types: ['GIFT_THING'],
      }),
    });
    await renderPage();
    await screen.findByLabelText(/Title/);

    expect(screen.queryByLabelText(/Price/)).toBeNull();
  });

  test('a library has its deposit; a stall does not', async () => {
    mockApi({
      coll: collection({ kind: 'LIBRARY', allowed_thing_types: ['LEND_THING', 'RENT_THING'] }),
    });
    const { container, unmount } = await renderPage();
    await waitFor(() => expect(container.querySelector('#add-thing-deposit')).toBeTruthy());
    unmount();

    mockApi();
    const stall = await renderPage();
    await screen.findByLabelText(/Title/);
    expect(stall.container.querySelector('#add-thing-deposit')).toBeNull();
  });
});

describe('AddThingPage — when the collection cannot be read', () => {
  // The form of a stall is all there is until the collection is known, so the page
  // says it could not read it; the server stays the gate, and "Create" stays usable.
  test('a failed read says so and leaves the form usable', async () => {
    apiFetch.mockImplementation(() =>
      Promise.resolve({ ok: false, status: 500, json: async () => ({}) })
    );
    await renderPage();

    expect(await screen.findByText('Error loading collection.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create' })).toBeEnabled();
  });

  test('a dropped connection says so and leaves the form usable', async () => {
    apiFetch.mockImplementation(() => Promise.reject(new Error('offline')));
    await renderPage();

    expect(await screen.findByText('Connection error.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create' })).toBeEnabled();
  });

  test('a collection that reads fine shows no error', async () => {
    mockApi();
    await renderPage();
    await screen.findByLabelText(/Title/);

    expect(screen.queryByText('Error loading collection.')).toBeNull();
    expect(screen.queryByText('Connection error.')).toBeNull();
  });
});

describe('AddThingPage — what the form sends', () => {
  test('a network’s form does not ask for a location: the pickup point says where', async () => {
    mockApi({
      coll: collection({
        kind: 'LIBRARY',
        mode: 'NETWORK',
        allowed_thing_types: ['LEND_THING', 'RENT_THING'],
      }),
    });
    const { container } = await renderPage();
    fireEvent.change(await screen.findByLabelText(/Title/), { target: { value: 'Drill' } });

    expect(container.querySelector('#add-thing-location')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(postBody()).toBeTruthy());
    expect(postBody()).not.toHaveProperty('location');
  });

  test('a stall gift sends its condition, its place and its availability', async () => {
    mockApi();
    const { container } = await renderPage();
    fireEvent.change(await screen.findByLabelText(/Title/), { target: { value: 'Blue pan' } });
    fireEvent.change(container.querySelector('#add-thing-location'), {
      target: { value: '  Gràcia  ' },
    });
    fireEvent.click(container.querySelector('#add-thing-condition-main-button'));
    fireEvent.click(await screen.findByRole('option', { name: 'Good condition' }));
    fireEvent.click(container.querySelector('#add-thing-availability-main-button'));
    fireEvent.click(await screen.findByRole('option', { name: 'Next week' }));

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(postBody()).toBeTruthy());
    expect(postBody()).toMatchObject({
      condition: 'GOOD',
      location: 'Gràcia',
      availability: 'NEXT_WEEK',
    });
  });

  test('a library rental sends its condition and place, and no availability: it has none to give', async () => {
    mockApi({
      coll: collection({ kind: 'LIBRARY', allowed_thing_types: ['LEND_THING', 'RENT_THING'] }),
    });
    const { container } = await renderPage();
    fireEvent.change(await screen.findByLabelText(/Title/), { target: { value: 'Drill' } });
    fireEvent.change(screen.getByLabelText(/Rental price/), { target: { value: '4' } });
    fireEvent.change(container.querySelector('#add-thing-location'), {
      target: { value: 'Sants' },
    });
    fireEvent.click(container.querySelector('#add-thing-condition-main-button'));
    fireEvent.click(await screen.findByRole('option', { name: 'Good condition' }));
    expect(container.querySelector('#add-thing-availability-main-button')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(postBody()).toBeTruthy());
    expect(postBody()).toMatchObject({ fee: '4', condition: 'GOOD', location: 'Sants' });
    expect(postBody()).not.toHaveProperty('availability');
  });

  test('a title is enough, and the collection travels with it', async () => {
    mockApi();
    await renderPage();
    fireEvent.change(await screen.findByLabelText(/Title/), { target: { value: 'Blue armchair' } });

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() =>
      expect(postBody()).toMatchObject({ headline: 'Blue armchair', collection_code: 'COL001' })
    );
    await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(navigate.mock.calls[0][0]).toBe('/collections/COL001');
  });

  // On a phone the collection page tells the person it worked and takes them to the
  // new card; for that it needs to know which card. The code
  // comes from the response of the POST, nowhere else.
  test('the new thing’s code, from the response, travels to the collection page', async () => {
    mockApi({ post: { ok: true, body: { code: 'NEW123', headline: 'Blue armchair' } } });
    await renderPage();
    fireEvent.change(await screen.findByLabelText(/Title/), { target: { value: 'Blue armchair' } });

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith('/collections/COL001', {
        state: { addedThing: 'NEW123' },
      })
    );
  });

  test('a response with no code still goes to the collection, with no state to act on', async () => {
    mockApi({ post: { ok: true, body: {} } });
    await renderPage();
    fireEvent.change(await screen.findByLabelText(/Title/), { target: { value: 'Blue armchair' } });

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/collections/COL001', undefined));
  });

  test('a title of only spaces is not a title', async () => {
    mockApi();
    await renderPage();
    fireEvent.change(await screen.findByLabelText(/Title/), { target: { value: '   ' } });

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('Title is required.')).toBeInTheDocument();
    expect(postBody()).toBeUndefined();
  });

  test('the endless toggle ships in a stall, and a library has none to ship', async () => {
    // `is_endless` is a gift-and-sale concept — a loan comes back by definition, so
    // sending the flag on one would be describing something that cannot happen.
    mockApi();
    const stall = await renderPage();
    fireEvent.change(await screen.findByLabelText(/Title/), { target: { value: 'Seed packets' } });
    fireEvent.click(screen.getByRole('button', { name: /Endless|Sin límite/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(postBody()?.is_endless).toBe(true));
    stall.unmount();

    apiFetch.mockClear();
    mockApi({
      coll: collection({ kind: 'LIBRARY', allowed_thing_types: ['LEND_THING', 'RENT_THING'] }),
    });
    await renderPage();
    fireEvent.change(await screen.findByLabelText(/Title/), { target: { value: 'A ladder' } });
    expect(screen.queryByRole('button', { name: /Endless|Sin límite/i })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(postBody()).toBeTruthy());
    expect(postBody()).not.toHaveProperty('is_endless');
  });

  test('a refused create shows the backend’s reason and keeps the form', async () => {
    mockApi({
      post: { ok: false, status: 400, body: { type: ['This group doesn’t take prices.'] } },
    });
    await renderPage();
    fireEvent.change(await screen.findByLabelText(/Title/), { target: { value: 'Blue armchair' } });
    navigate.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('This group doesn’t take prices.')).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
  });

  test('a refusal the server coded is said in the reader’s language, not in its English', async () => {
    mockApi({
      post: {
        ok: false,
        status: 400,
        body: { type: ['This group doesn’t take prices.'], code: 'no_prices_here' },
      },
    });
    await renderPage();
    fireEvent.change(await screen.findByLabelText(/Title/), { target: { value: 'Blue armchair' } });

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText(en.requestErrors.no_prices_here)).toBeInTheDocument();
    expect(screen.queryByText('This group doesn’t take prices.')).toBeNull();
  });

  test('a rate-limited create says "too many", not "error"', async () => {
    // 429 means "try later"; a generic failure message would send the member
    // back to edit a form that was already correct.
    mockApi({ post: { ok: false, status: 429, body: {} } });
    await renderPage();
    fireEvent.change(await screen.findByLabelText(/Title/), { target: { value: 'Blue armchair' } });

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText(/[Tt]oo many/)).toBeInTheDocument();
  });
});

describe('AddThingPage — the deployment’s policy, asked about the verb the price makes', () => {
  // A deployment that gives gifts and sales to everyone and loans and rentals after
  // approval (a library's two verbs) — or one that gives gifts and not sales.
  const policy = (thing_types) => ({
    collection_modes: ['PROPRIETARY', 'COMMUNITY'],
    thing_types,
    request_url: '/request-access/',
  });

  const mockPolicy = (coll, capabilities) =>
    apiFetch.mockImplementation((url, opts) => {
      if (opts?.method === 'POST')
        return Promise.resolve({ ok: true, status: 201, json: async () => ({}) });
      if (url.includes('/auth/me/'))
        return Promise.resolve({ ok: true, status: 200, json: async () => ({ capabilities }) });
      return Promise.resolve({ ok: true, status: 200, json: async () => coll });
    });

  beforeEach(() => {
    // useCapabilities caches per account at module scope; a fresh code keeps this
    // from inheriting what the tests above left behind.
    localStorage.setItem('userCode', `MEMBER${Math.random()}`);
  });

  test('a price in a stall whose policy does not give sales shows the notice and cannot be sent', async () => {
    mockPolicy(collection(), policy(['GIFT_THING']));
    await renderPage();
    fireEvent.change(await screen.findByLabelText(/Title/), { target: { value: 'Old bike' } });
    // No price: a gift, which is given — nothing to explain, and it can be sent.
    expect(screen.queryByText(/need approval/i)).toBeNull();

    fireEvent.change(screen.getByLabelText(/Price/), { target: { value: '30' } });

    expect(await screen.findByText(/need approval on this deployment: Sale/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled();
    expect(postBody()).toBeUndefined();

    fireEvent.change(screen.getByLabelText(/Price/), { target: { value: '' } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create' })).toBeEnabled());
  });

  test('a member of a community library may lend what its owner allowed, whatever the policy says of them', async () => {
    mockPolicy(
      collection({
        kind: 'LIBRARY',
        mode: 'COMMUNITY',
        is_member: true,
        allowed_thing_types: ['LEND_THING', 'RENT_THING'],
      }),
      policy(['GIFT_THING', 'SELL_THING'])
    );
    await renderPage();
    fireEvent.change(await screen.findByLabelText(/Title/), { target: { value: 'A ladder' } });

    // Neither the loan nor, with a price, the rental is withheld here.
    expect(screen.queryByText(/need approval/i)).toBeNull();
    fireEvent.change(screen.getByLabelText(/Rental price/), { target: { value: '3' } });
    expect(screen.queryByText(/need approval/i)).toBeNull();
    expect(screen.getByRole('button', { name: 'Create' })).toBeEnabled();
  });

  test('an unvetted account in a proprietary library is held to the policy for its loans', async () => {
    mockPolicy(
      collection({ kind: 'LIBRARY', allowed_thing_types: ['LEND_THING', 'RENT_THING'] }),
      policy(['GIFT_THING', 'SELL_THING'])
    );
    await renderPage();
    await screen.findByLabelText(/Title/);

    expect(await screen.findByText(/need approval on this deployment: Lend/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled();
  });
});

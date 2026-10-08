import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

window.scrollTo = vi.fn();

// The real error readers are kept: the join's refusal is worded by them.
vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal()),
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import ThingLinkbox from '../components/ThingLinkbox';
import ThingPage from '../pages/ThingPage';
import RequestThingPage from '../pages/RequestThingPage';

// Asking for any thing is being part of the group that lists it. The server
// answers `not_a_member` to someone who only reads a PUBLIC group; the client
// joins them and asks once more — and only for that marker.

const res = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
const NOT_A_MEMBER = res(
  { error: 'You need to be a member of this group to ask for this.', code: 'not_a_member' },
  403
);
const JOINED_NOTICE = "To ask here you've joined Taller. You can leave it from your profile.";

const gift = (over = {}) => ({
  code: 'THG001',
  type: 'GIFT_THING',
  headline: 'Lamp',
  status: 'ACTIVE',
  owner: 'OWNER1',
  owner_name: 'Lele',
  thumbnail_url: '',
  gallery_urls: [],
  transfer_count: 0,
  ...over,
});

const joinUrls = () =>
  apiFetch.mock.calls
    .filter(([u, o]) => /\/join\/$/.test(u) && o?.method === 'POST')
    .map(([u]) => u);
const requestPosts = () =>
  apiFetch.mock.calls.filter(
    ([u, o]) => /\/things\/[^/]+\/request\/$/.test(u) && o?.method === 'POST'
  );

/** The server: the first request is refused as given, later ones answer `retry`. */
function server({ first = NOT_A_MEMBER, retry = res({}, 201), join = res({}), thing = {} } = {}) {
  let asked = 0;
  apiFetch.mockImplementation((url, opts = {}) => {
    if (/\/join\/$/.test(url) && opts.method === 'POST') return Promise.resolve(join);
    if (/\/things\/[^/]+\/request\/$/.test(url) && opts.method === 'POST') {
      asked += 1;
      return Promise.resolve(asked === 1 ? first : retry);
    }
    if (/\/calendar\//.test(url)) return Promise.resolve(res([]));
    if (/\/faq\//.test(url)) return Promise.resolve(res({ results: [] }));
    if (/\/transfers\//.test(url))
      return Promise.resolve(res({ total_transfers: 0, transfers: [] }));
    if (/\/things\/[^/]+\/(\?.*)?$/.test(url)) return Promise.resolve(res(thing));
    return Promise.resolve(res({}));
  });
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'GUEST1');
  localStorage.setItem('koro', 'basic');
  vi.clearAllMocks();
});

describe('a gift asked for from a card', () => {
  const renderCard = (props = {}) => {
    const onJoinedGroup = vi.fn();
    render(
      <MemoryRouter>
        <ThingLinkbox
          thing={gift()}
          userCode="GUEST1"
          collectionCode="COL001"
          collectionHeadline="Taller"
          onUpdateThing={() => {}}
          onJoinedGroup={onJoinedGroup}
          {...props}
        />
      </MemoryRouter>
    );
    return { onJoinedGroup };
  };
  const claim = () => fireEvent.click(screen.getByRole('button', { name: 'Claim' }));

  test('a refused request joins the page’s group, asks again once and says both', async () => {
    server();
    const { onJoinedGroup } = renderCard();

    claim();

    expect(
      await screen.findByText(`Request sent — you'll hear back soon. ${JOINED_NOTICE}`)
    ).toBeInTheDocument();
    expect(joinUrls()).toEqual(['/api/v1/collections/COL001/join/']);
    expect(requestPosts()).toHaveLength(2);
    expect(onJoinedGroup).toHaveBeenCalledTimes(1);
  });

  test('a 403 without the marker never joins anybody', async () => {
    server({ first: res({ error: 'Not authorized to request this thing' }, 403) });
    const { onJoinedGroup } = renderCard();

    claim();

    expect(await screen.findByText('Error sending request.')).toBeInTheDocument();
    expect(joinUrls()).toEqual([]);
    expect(requestPosts()).toHaveLength(1);
    expect(onJoinedGroup).not.toHaveBeenCalled();
  });

  test('a join that is refused says why and asks for nothing', async () => {
    server({ join: res({ detail: "This collection has taken today's joins." }, 429) });
    const { onJoinedGroup } = renderCard();

    claim();

    expect(await screen.findByText("This collection has taken today's joins.")).toBeInTheDocument();
    expect(requestPosts()).toHaveLength(1);
    expect(onJoinedGroup).not.toHaveBeenCalled();
  });

  test('a retry that fails after joining shows its own reason, and the page still hears of the join', async () => {
    server({ retry: res({ error: 'x' }, 500) });
    const { onJoinedGroup } = renderCard();

    claim();

    expect(await screen.findByText('Error sending request.')).toBeInTheDocument();
    expect(onJoinedGroup).toHaveBeenCalledTimes(1);
  });

  test('a card with no group of its own joins nobody', async () => {
    server();
    renderCard({ collectionCode: undefined });

    claim();

    await screen.findByText('Error sending request.');
    expect(joinUrls()).toEqual([]);
  });
});

describe('a gift asked for from its own page', () => {
  const renderPage = (path, route) => {
    render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={<ThingPage />} />
          <Route path="*" element={<div />} />
        </Routes>
      </MemoryRouter>
    );
  };
  const claim = async () => fireEvent.click(await screen.findByRole('button', { name: 'Claim' }));
  const thing = gift({ collection_code: 'COL001', collection_headline: 'Taller' });

  test('joins the collection the server resolved, and says so', async () => {
    server({ thing });
    renderPage('/collections/COL001/things/THG001', '/collections/:code/things/:thingCode');

    await claim();

    expect(
      await screen.findByText(`Request sent — you'll hear back soon. ${JOINED_NOTICE}`)
    ).toBeInTheDocument();
    expect(joinUrls()).toEqual(['/api/v1/collections/COL001/join/']);
  });

  test('on the standalone route it joins the one the server picked', async () => {
    server({ thing });
    renderPage('/things/THG001', '/things/:thingCode');

    await claim();

    await screen.findByText(/You can leave it from your profile/);
    expect(joinUrls()).toEqual(['/api/v1/collections/COL001/join/']);
  });

  test('a route naming another group than the one resolved joins nobody', async () => {
    server({ thing });
    renderPage('/collections/OTHER1/things/THG001', '/collections/:code/things/:thingCode');

    await claim();

    await screen.findByText('Error sending request.');
    expect(joinUrls()).toEqual([]);
  });
});

describe('a loan asked for on its request page', () => {
  const LOAN = {
    code: 'LEND01',
    type: 'LEND_THING',
    headline: 'Ladder',
    fee: null,
    collection_code: 'COL001',
    collection_headline: 'Taller',
    rental_durations: [],
    rental_weekdays: [],
    available_today: true,
    next_available: null,
  };
  const renderLoan = () =>
    render(
      <MemoryRouter
        initialEntries={[{ pathname: '/collections/COL001/things/LEND01/request', state: {} }]}
      >
        <Routes>
          <Route
            path="/collections/:code/things/:thingCode/request"
            element={<RequestThingPage />}
          />
          <Route path="*" element={<div />} />
        </Routes>
      </MemoryRouter>
    );
  const send = async (container) => {
    await screen.findAllByRole('button', { name: 'Choose date' });
    for (const [selector, value] of [
      ['#request-start-date', '03/06/2099'],
      ['#request-end-date', '05/06/2099'],
    ]) {
      const input = container.querySelector(selector);
      fireEvent.change(input, { target: { value } });
      fireEvent.blur(input);
    }
    fireEvent.click(screen.getByRole('button', { name: /^(Hold|Borrow|Request)/ }));
  };

  test('joins, asks again with the same dates and says it joined “to ask”', async () => {
    server({ thing: LOAN });
    const view = renderLoan();

    await send(view.container);

    expect(await screen.findByText(JOINED_NOTICE)).toBeInTheDocument();
    expect(joinUrls()).toEqual(['/api/v1/collections/COL001/join/']);
    const [first, second] = requestPosts();
    expect(second[1].body).toBe(first[1].body);
    await waitFor(() => expect(screen.queryByText(/You're all set/)).toBeInTheDocument());
  });

  test('a 403 without the marker joins nobody', async () => {
    server({ thing: LOAN, first: res({ error: 'Not authorized' }, 403) });
    const view = renderLoan();

    await send(view.container);

    await waitFor(() => expect(requestPosts()).toHaveLength(1));
    expect(joinUrls()).toEqual([]);
  });
});

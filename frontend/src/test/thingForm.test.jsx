import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
  ),
  extractApiError: vi.fn(() => Promise.resolve('')),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import AddThingPage from '../pages/AddThingPage';
import EditThingPage from '../pages/EditThingPage';

function mockResponse(data, ok = true) {
  return { ok, status: ok ? 200 : 400, json: () => Promise.resolve(data) };
}

// `collection` feeds AddThingPage's collection fetch (drives type/field gating);
// `thing` feeds EditThingPage's load fetch and PATCH save.
function setApi({ collection = {}, thing = {} } = {}) {
  apiFetch.mockImplementation((url, opts = {}) => {
    const method = opts.method || 'GET';
    if (url === '/api/v1/things/' && method === 'POST')
      return Promise.resolve(mockResponse({ code: 'NEW001' }));
    if (/\/collections\/[^/]+\//.test(url)) return Promise.resolve(mockResponse(collection));
    if (/\/things\/[^/]+\//.test(url)) return Promise.resolve(mockResponse(thing));
    return Promise.resolve(mockResponse({}));
  });
}

function renderAdd(apiOpts) {
  setApi(apiOpts);
  return render(
    <MemoryRouter initialEntries={['/collections/COL001/add']}>
      <Routes>
        <Route path="/collections/:code/add" element={<AddThingPage />} />
        <Route path="*" element={<div data-testid="navigated" />} />
      </Routes>
    </MemoryRouter>
  );
}

function renderEdit(apiOpts) {
  setApi(apiOpts);
  return render(
    <MemoryRouter initialEntries={['/things/THG001/edit']}>
      <Routes>
        <Route path="/things/:thingCode/edit" element={<EditThingPage />} />
        <Route path="*" element={<div data-testid="navigated" />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ABC123');
  localStorage.setItem(
    'theeemeColors',
    JSON.stringify({
      color_01: 'bus',
      color_02: 'suomenlinna-light',
      color_03: 'copper',
      color_04: 'black',
      color_05: 'white',
      color_06: 'white',
    })
  );
  localStorage.setItem('koro', 'basic');
  vi.clearAllMocks();
  setApi();
});

// ════════════════════════════════════════════════════════════════════════
// AddThingPage — field visibility per kind of collection
//
// The fields follow the collection's kind, never the verb its price makes, so
// typing a price does not make another field appear or vanish.
// ════════════════════════════════════════════════════════════════════════
describe('AddThingPage — field visibility', () => {
  test('a stall: price, the endless switch, availability, condition, place, photos', async () => {
    const { container } = renderAdd({
      collection: { kind: 'STALL', headline: 'Plain', mode: 'PROPRIETARY' },
    });

    await waitFor(() => expect(container.querySelector('#add-thing-headline')).toBeTruthy());
    expect(container.querySelector('#add-thing-fee')).toBeTruthy();
    expect(container.querySelector('#add-thing-is-endless')).toBeTruthy();
    expect(screen.getByText('Availability')).toBeInTheDocument();
    expect(screen.getByText('Condition')).toBeInTheDocument();
    expect(container.querySelector('#add-thing-location')).toBeTruthy();
    expect(container.querySelector('#add-thing-deposit')).toBeNull();
    expect(screen.getByText('More photos')).toBeInTheDocument();
    expect(screen.getByText('Thumbnail')).toBeInTheDocument();
  });

  test('a library: rental price, deposit, condition and place — and no static availability', async () => {
    const { container } = renderAdd({
      collection: { kind: 'LIBRARY', mode: 'PROPRIETARY' },
    });

    await waitFor(() => expect(container.querySelector('#add-thing-deposit')).toBeTruthy());
    expect(container.querySelector('#add-thing-fee')).toBeTruthy();
    expect(container.querySelector('#add-thing-is-endless')).toBeNull();
    // A loan and a rental show their *live* availability from the calendar, so a
    // static hint would be data that never surfaces.
    expect(screen.queryByText('Availability')).toBeNull();
    expect(screen.getByText('Condition')).toBeInTheDocument();
    expect(container.querySelector('#add-thing-location')).toBeTruthy();
  });

  test('a shed: an optional price and a place, nothing of a loan or a gift', async () => {
    const { container } = renderAdd({
      collection: { kind: 'SHED', mode: 'PROPRIETARY', allowed_thing_types: ['RESERVE_THING'] },
    });

    await waitFor(() => expect(container.querySelector('#add-thing-headline')).toBeTruthy());
    expect(container.querySelector('#add-thing-fee')).toBeTruthy();
    expect(container.querySelector('#add-thing-deposit')).toBeNull();
    expect(container.querySelector('#add-thing-is-endless')).toBeNull();
    expect(screen.queryByText('Availability')).toBeNull();
    expect(screen.getByText('Condition')).toBeInTheDocument();
    expect(container.querySelector('#add-thing-location')).toBeTruthy();
  });

  test.each([
    ['STALL', 'Price (optional)', "No price, it's a gift."],
    ['LIBRARY', 'Rental price (optional)', "No price, it's lent for free."],
  ])('a %s says what no price means', async (kind, label, help) => {
    const { container } = renderAdd({ collection: { kind, mode: 'PROPRIETARY' } });

    await waitFor(() => expect(container.querySelector('#add-thing-fee')).toBeTruthy());
    expect(container.querySelector('label[for="add-thing-fee"]')).toHaveTextContent(label);
    expect(screen.getByText(help)).toBeInTheDocument();
  });

  test.each([
    ['STALL', ['GIFT_THING']],
    ['LIBRARY', ['LEND_THING']],
  ])(
    'a community %s whose members may not set a price has no price field',
    async (kind, allowed) => {
      const { container } = renderAdd({
        collection: { kind, mode: 'COMMUNITY', allowed_thing_types: allowed },
      });

      await waitFor(() => expect(container.querySelector('#add-thing-headline')).toBeTruthy());
      expect(container.querySelector('#add-thing-fee')).toBeNull();
    }
  );

  test('there is no selector of verbs, and nothing explaining them', async () => {
    const { container } = renderAdd({ collection: { kind: 'STALL', mode: 'PROPRIETARY' } });

    await waitFor(() => expect(container.querySelector('#add-thing-headline')).toBeTruthy());
    expect(container.querySelector('#add-thing-type-main-button')).toBeNull();
    expect(screen.queryByRole('button', { name: 'What each type means' })).toBeNull();
  });
});

// ════════════════════════════════════════════════════════════════════════
// AddThingPage — submit payload
// ════════════════════════════════════════════════════════════════════════
describe('AddThingPage — submit', () => {
  test('POSTs to /api/v1/things/ with headline and collection_code, and no type', async () => {
    const { container } = renderAdd({ collection: { kind: 'STALL', mode: 'PROPRIETARY' } });

    await waitFor(() => expect(container.querySelector('#add-thing-headline')).toBeTruthy());
    fireEvent.change(container.querySelector('#add-thing-headline'), {
      target: { value: 'My Gift' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      const call = apiFetch.mock.calls.find(
        (c) => c[0] === '/api/v1/things/' && c[1]?.method === 'POST'
      );
      expect(call).toBeTruthy();
      const body = JSON.parse(call[1].body);
      expect(body).toMatchObject({ headline: 'My Gift', collection_code: 'COL001' });
      // The server puts the verb, from the kind and the price.
      expect(body).not.toHaveProperty('type');
    });
  });
});

// ════════════════════════════════════════════════════════════════════════
// EditThingPage — pre-population + PATCH
// ════════════════════════════════════════════════════════════════════════
describe('EditThingPage', () => {
  test('pre-populates the headline from the loaded thing', async () => {
    renderEdit({
      thing: { code: 'THG001', type: 'GIFT_THING', headline: 'Existing Thing', description: '' },
    });

    expect(await screen.findByDisplayValue('Existing Thing')).toBeInTheDocument();
  });

  test('PATCHes /api/v1/things/{code}/ with the edited fields', async () => {
    const { container } = renderEdit({
      thing: {
        code: 'THG001',
        type: 'GIFT_THING',
        collection_kind: 'STALL',
        headline: 'Existing Thing',
        description: '',
      },
    });

    await screen.findByDisplayValue('Existing Thing');
    fireEvent.change(container.querySelector('#edit-thing-headline'), {
      target: { value: 'Renamed Thing' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      const call = apiFetch.mock.calls.find(
        (c) => c[0] === '/api/v1/things/THG001/' && c[1]?.method === 'PATCH'
      );
      expect(call).toBeTruthy();
      const body = JSON.parse(call[1].body);
      expect(body).toMatchObject({ headline: 'Renamed Thing' });
      expect(body).not.toHaveProperty('type');
    });
  });
});

// ════════════════════════════════════════════════════════════════════════
// EditThingPage — a deployment that has narrowed since the thing was offered
// ════════════════════════════════════════════════════════════════════════

describe('EditThingPage — the policy is asked about the verb the price makes', () => {
  /* A deployment that has stopped handing out one verb still lets a thing stay as it is
     — the server judges only a **change** — but a price that would turn a gift into a
     sale it does not give shows the "needs approval" notice and cannot be saved. The
     same for the other way round: what a thing already is is never withheld from it. */
  const caps = (thing_types) => ({
    collection_modes: ['PROPRIETARY'],
    thing_types,
    request_url: 'https://example.test/ask/',
  });

  function apiWith(thing, capabilities) {
    apiFetch.mockImplementation((url) => {
      if (url.includes('/auth/me/')) {
        return Promise.resolve(mockResponse({ capabilities }));
      }
      return Promise.resolve(mockResponse(thing));
    });
  }

  beforeEach(() => {
    // The capabilities cache is module-scope and keyed by account; a fresh code
    // keeps this independent of the tests above, which answer /auth/me/ with {}.
    localStorage.setItem('userCode', `NARROW${Math.random()}`);
  });

  const open = () =>
    render(
      <MemoryRouter initialEntries={['/things/THG001/edit']}>
        <Routes>
          <Route path="/things/:thingCode/edit" element={<EditThingPage />} />
        </Routes>
      </MemoryRouter>
    );

  test('a price that would make a sale the policy does not give shows the notice and blocks Save', async () => {
    apiWith(
      { code: 'THG001', type: 'GIFT_THING', collection_kind: 'STALL', headline: 'Vase', tags: [] },
      caps(['GIFT_THING'])
    );
    const { container } = open();
    await waitFor(() => expect(container.querySelector('#edit-thing-fee')).toBeTruthy());
    // As it stands it is a gift, which is given: nothing to explain.
    expect(screen.queryByText(/need approval/)).toBeNull();
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();

    fireEvent.change(container.querySelector('#edit-thing-fee'), { target: { value: '5' } });

    expect(await screen.findByText(/need approval on this deployment: Sale/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();

    fireEvent.change(container.querySelector('#edit-thing-fee'), { target: { value: '' } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled());
  });

  test('a thing already offered under a verb the policy no longer gives stays editable', async () => {
    apiWith(
      {
        code: 'THG001',
        type: 'LEND_THING',
        collection_kind: 'LIBRARY',
        headline: 'Drill',
        tags: [],
      },
      caps(['GIFT_THING', 'SELL_THING'])
    );
    const { container } = open();
    await waitFor(() => expect(container.querySelector('#edit-thing-fee')).toBeTruthy());

    expect(screen.queryByText(/need approval/)).toBeNull();
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
  });

  test('a loan a stall kept stays what it is, whatever its price would make it elsewhere', async () => {
    // The server leaves such a thing's verb alone (it is not one of the stall's); the
    // form must not ask the policy about the rental its price would be in a library.
    apiWith(
      {
        code: 'THG001',
        type: 'LEND_THING',
        collection_kind: 'STALL',
        headline: 'Old drill',
        fee: '5.00',
        tags: [],
      },
      caps(['GIFT_THING', 'SELL_THING'])
    );
    const { container } = open();
    await waitFor(() => expect(container.querySelector('#edit-thing-fee')).toBeTruthy());

    expect(screen.queryByText(/need approval/)).toBeNull();
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
  });
});

// ════════════════════════════════════════════════════════════════════════
// ThingForm — the two controls that do more than copy a keystroke
// ════════════════════════════════════════════════════════════════════════

describe('AddThingPage — picking one of the collection’s tags', () => {
  /* A tag label may itself be one text per language, and the reader picks from
     the *resolved* labels while the vocabulary — and the thing — stores the raw
     value. Saving what the owner read instead of what they picked would put a
     string outside the collection's vocabulary onto the thing (the server
     checks tags against it), and would freeze one language into data every
     other member reads in theirs. */
  const KITCHEN = '{"es":"Cocina","ca":"Cuina","en":"Kitchen"}';

  test('stores the tag’s own value, not the label it was read as', async () => {
    const { container } = renderAdd({
      collection: { mode: 'PROPRIETARY', tags: [KITCHEN, 'garden'] },
    });

    await waitFor(() => expect(container.querySelector('#add-thing-headline')).toBeTruthy());
    fireEvent.change(container.querySelector('#add-thing-headline'), {
      target: { value: 'Blue pan' },
    });

    // The list offers the reader's language …
    fireEvent.click(container.querySelector('#add-thing-tags-main-button'));
    fireEvent.click(await screen.findByRole('option', { name: 'Kitchen' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      const call = apiFetch.mock.calls.find(
        (c) => c[0] === '/api/v1/things/' && c[1]?.method === 'POST'
      );
      expect(call).toBeTruthy();
      // … and the thing keeps the value every language resolves from.
      expect(JSON.parse(call[1].body).tags).toEqual([KITCHEN]);
    });
  });
});

describe('AddThingPage — clearing a detail select', () => {
  /* Both selects are `clearable`, and clearing hands the change back an empty
     array. Reading `[0].value` off it throws inside the render tree, which in
     this app means the whole add-a-thing form disappears — for someone whose
     only mistake was changing their mind about "Immediate". */
  test('changing your mind about availability empties it instead of breaking', async () => {
    const { container } = renderAdd({ collection: { mode: 'PROPRIETARY' } });

    await waitFor(() => expect(container.querySelector('#add-thing-headline')).toBeTruthy());
    fireEvent.change(container.querySelector('#add-thing-headline'), {
      target: { value: 'Blue pan' },
    });

    fireEvent.click(container.querySelector('#add-thing-availability-main-button'));
    fireEvent.click(await screen.findByRole('option', { name: 'Immediate' }));
    // The clear control is found by the choice it would undo, because HDS's own
    // wording for it is not in the reader's language here — `language="en"` as a
    // prop stopped being honoured in HDS 6 (see ShareCollectionMenu, which puts
    // it inside `texts`), so this button currently announces itself in Finnish.
    // Matching the quoted option instead keeps this test true either way.
    fireEvent.click(screen.getByRole('button', { name: /"Immediate"/ }));

    // Still standing, still submittable — and nothing was carried over.
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      const call = apiFetch.mock.calls.find(
        (c) => c[0] === '/api/v1/things/' && c[1]?.method === 'POST'
      );
      expect(call).toBeTruthy();
      expect(JSON.parse(call[1].body).availability).toBeUndefined();
    });
  });
});

// ════════════════════════════════════════════════════════════════════════
// Deposit — LEND/RENT only, and never left ambiguous across an edit
// ════════════════════════════════════════════════════════════════════════

describe('AddThingPage — the deposit field only exists in a library', () => {
  test('a stall never has a deposit input', async () => {
    const { container } = renderAdd({
      collection: { kind: 'STALL', headline: 'Plain', mode: 'PROPRIETARY' },
    });

    await waitFor(() => expect(container.querySelector('#add-thing-headline')).toBeTruthy());
    expect(container.querySelector('#add-thing-deposit')).toBeNull();
  });

  test('a library that only lends gets the field, with no default and never labelled as part of the price', async () => {
    const { container } = renderAdd({
      collection: { kind: 'LIBRARY', mode: 'COMMUNITY', allowed_thing_types: ['LEND_THING'] },
    });

    await waitFor(() => expect(container.querySelector('#add-thing-deposit')).toBeTruthy());
    // Empty, never pre-filled (DESIGN §6 — no suggested amount).
    expect(container.querySelector('#add-thing-deposit').value).toBe('');
    // A group that lends and does not rent has no price row: a shared euro icon with
    // no other cue is exactly how "10 + 50" becomes "60 €".
    expect(container.querySelector('#add-thing-fee')).toBeNull();
  });

  test('a library carries both fields, distinctly labelled', async () => {
    const { container } = renderAdd({
      collection: { kind: 'LIBRARY', mode: 'PROPRIETARY' },
    });

    await waitFor(() => expect(container.querySelector('#add-thing-fee')).toBeTruthy());
    expect(container.querySelector('#add-thing-deposit')).toBeTruthy();
    // Two different labels, not the same word twice — otherwise "10" next to
    // "50" reads as one 60 € cost instead of a price plus a returnable deposit.
    const feeLabel = container.querySelector('label[for="add-thing-fee"]');
    const depositLabel = container.querySelector('label[for="add-thing-deposit"]');
    expect(feeLabel.textContent).not.toBe(depositLabel.textContent);
    expect(depositLabel.textContent).toMatch(/deposit/i);
  });

  test('a deposit typed for a LEND thing reaches the POST body', async () => {
    const { container } = renderAdd({
      collection: { kind: 'LIBRARY', mode: 'COMMUNITY', allowed_thing_types: ['LEND_THING'] },
    });

    await waitFor(() => expect(container.querySelector('#add-thing-deposit')).toBeTruthy());
    fireEvent.change(container.querySelector('#add-thing-headline'), {
      target: { value: 'Drill' },
    });
    fireEvent.change(container.querySelector('#add-thing-deposit'), { target: { value: '50' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      const call = apiFetch.mock.calls.find(
        (c) => c[0] === '/api/v1/things/' && c[1]?.method === 'POST'
      );
      expect(call).toBeTruthy();
      expect(JSON.parse(call[1].body)).toMatchObject({ deposit: '50' });
    });
  });

  test('leaving it empty never sends the field at all — nothing to clear on a brand-new thing', async () => {
    const { container } = renderAdd({
      collection: { kind: 'LIBRARY', mode: 'COMMUNITY', allowed_thing_types: ['LEND_THING'] },
    });

    await waitFor(() => expect(container.querySelector('#add-thing-deposit')).toBeTruthy());
    fireEvent.change(container.querySelector('#add-thing-headline'), {
      target: { value: 'Drill' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      const call = apiFetch.mock.calls.find(
        (c) => c[0] === '/api/v1/things/' && c[1]?.method === 'POST'
      );
      expect(call).toBeTruthy();
      expect(JSON.parse(call[1].body)).not.toHaveProperty('deposit');
    });
  });
});

describe('EditThingPage — deposit follows the type, explicitly', () => {
  test('a stored deposit pre-fills the field', async () => {
    const { container } = renderEdit({
      thing: {
        code: 'THG001',
        type: 'LEND_THING',
        collection_kind: 'LIBRARY',
        headline: 'Drill',
        deposit: '50.00',
      },
    });

    await waitFor(() => expect(container.querySelector('#edit-thing-deposit')).toBeTruthy());
    expect(container.querySelector('#edit-thing-deposit').value).toBe('50');
  });

  test('the deposit is sent as null from a kind that has none, so a stored one cannot outlive it', async () => {
    // The server judges the row that lands (core/serializers/CLAUDE.md): an untouched
    // field keeps its stored value, so a thing in a stall that somehow carries a
    // deposit has to clear it itself or the save 400s.
    const { container } = renderEdit({
      thing: {
        code: 'THG001',
        type: 'GIFT_THING',
        collection_kind: 'STALL',
        headline: 'Vase',
        deposit: '50.00',
      },
    });
    await waitFor(() => expect(container.querySelector('#edit-thing-fee')).toBeTruthy());
    expect(container.querySelector('#edit-thing-deposit')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      const call = apiFetch.mock.calls.find(
        (c) => c[0] === '/api/v1/things/THG001/' && c[1]?.method === 'PATCH'
      );
      expect(call).toBeTruthy();
      expect(JSON.parse(call[1].body).deposit).toBeNull();
    });
  });

  test('a library keeps sending the amount', async () => {
    const { container } = renderEdit({
      thing: {
        code: 'THG001',
        type: 'LEND_THING',
        collection_kind: 'LIBRARY',
        headline: 'Drill',
        deposit: '50.00',
      },
    });
    await waitFor(() => expect(container.querySelector('#edit-thing-deposit')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      const call = apiFetch.mock.calls.find(
        (c) => c[0] === '/api/v1/things/THG001/' && c[1]?.method === 'PATCH'
      );
      expect(call).toBeTruthy();
      expect(JSON.parse(call[1].body).deposit).toBe('50.00');
    });
  });
});

describe('a text that opens like a language map and is not one', () => {
  // A map that parses already shows in the counter ("es 4/64 · ca 2/64"); a broken
  // one counted like prose and then showed on the card with its braces, and nothing
  // on the form said so.
  test('the headline and description say they will read as plain text', async () => {
    const { container } = renderAdd({ collection: { allowed_thing_types: ['GIFT_THING'] } });
    const headline = await waitFor(() => {
      const el = container.querySelector('input[id$="-headline"]');
      expect(el).not.toBeNull();
      return el;
    });
    const description = container.querySelector('textarea[id$="-description"]');
    const warning = /Read as plain text/;

    fireEvent.change(headline, { target: { value: '{"es": "Taladro", "ca": "Trepant",}' } });
    expect(screen.getByText(warning)).toBeInTheDocument();

    fireEvent.change(headline, { target: { value: '{"es": "Taladro", "ca": "Trepant"}' } });
    expect(screen.queryByText(warning)).not.toBeInTheDocument();
    expect(screen.getByText('es 7/64 · ca 7/64')).toBeInTheDocument();

    fireEvent.change(description, { target: { value: '{"es": "Funciona"' } });
    expect(screen.getByText(warning)).toBeInTheDocument();
  });
});

// ════════════════════════════════════════════════════════════════════════
// EditThingPage — the price puts the verb, so the price is what is edited
// ════════════════════════════════════════════════════════════════════════
describe('EditThingPage — what a save sends', () => {
  const patch = () => {
    const call = apiFetch.mock.calls.find(
      (c) => c[0] === '/api/v1/things/THG001/' && c[1]?.method === 'PATCH'
    );
    return call && JSON.parse(call[1].body);
  };

  const sale = {
    code: 'THG001',
    type: 'SELL_THING',
    collection_kind: 'STALL',
    collection_allowed_thing_types: ['GIFT_THING', 'SELL_THING'],
    headline: 'Bike',
    fee: '30.00',
  };

  test('a price is sent as typed, and no verb with it', async () => {
    const { container } = renderEdit({ thing: sale });
    await waitFor(() => expect(container.querySelector('#edit-thing-fee')).toBeTruthy());

    fireEvent.change(container.querySelector('#edit-thing-fee'), { target: { value: '25' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(patch()).toBeTruthy());
    expect(patch().fee).toBe('25');
    expect(patch()).not.toHaveProperty('type');
  });

  test('clearing the price is said, so the sale becomes a gift again', async () => {
    const { container } = renderEdit({ thing: sale });
    await waitFor(() => expect(container.querySelector('#edit-thing-fee')).toBeTruthy());

    fireEvent.change(container.querySelector('#edit-thing-fee'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(patch()).toBeTruthy());
    expect(patch().fee).toBeNull();
  });

  test('a community group whose members may not set a price has no price to edit or send', async () => {
    const { container } = renderEdit({
      thing: {
        ...sale,
        type: 'GIFT_THING',
        fee: null,
        collection_allowed_thing_types: ['GIFT_THING'],
      },
    });
    await waitFor(() => expect(container.querySelector('#edit-thing-headline')).toBeTruthy());
    expect(container.querySelector('#edit-thing-fee')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(patch()).toBeTruthy());
    expect(patch()).not.toHaveProperty('fee');
  });

  test('the endless switch is a stall’s, and a library’s thing has none', async () => {
    const stall = renderEdit({ thing: sale });
    await waitFor(() =>
      expect(stall.container.querySelector('#edit-thing-is-endless')).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(patch()).toHaveProperty('is_endless'));
    stall.unmount();

    apiFetch.mockClear();
    const library = renderEdit({
      thing: {
        code: 'THG001',
        type: 'LEND_THING',
        collection_kind: 'LIBRARY',
        collection_allowed_thing_types: ['LEND_THING', 'RENT_THING'],
        headline: 'Drill',
      },
    });
    await waitFor(() => expect(library.container.querySelector('#edit-thing-fee')).toBeTruthy());
    expect(library.container.querySelector('#edit-thing-is-endless')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(patch()).toBeTruthy());
    expect(patch()).not.toHaveProperty('is_endless');
  });

  test('a thing that is endless is loaded as endless, and a save of another field keeps it so', async () => {
    const { container } = renderEdit({ thing: { ...sale, is_endless: true } });
    await waitFor(() => expect(container.querySelector('#edit-thing-is-endless')).toBeTruthy());
    expect(container.querySelector('#edit-thing-is-endless')).toHaveAttribute(
      'aria-pressed',
      'true'
    );

    fireEvent.change(container.querySelector('#edit-thing-headline'), {
      target: { value: 'Bike, retitled' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(patch()).toBeTruthy());
    expect(patch().headline).toBe('Bike, retitled');
    expect(patch().is_endless).toBe(true);
  });

  test('a loan a mixed stall kept is edited as a loan: its deposit stays, the stall’s switch does not appear', async () => {
    const { container } = renderEdit({
      thing: {
        code: 'THG001',
        type: 'LEND_THING',
        collection_kind: 'STALL',
        collection_allowed_thing_types: ['GIFT_THING', 'SELL_THING'],
        headline: 'Old drill',
        deposit: '20.00',
        availability: 'IMMEDIATE',
      },
    });
    await waitFor(() => expect(container.querySelector('#edit-thing-deposit')).toBeTruthy());
    expect(container.querySelector('#edit-thing-is-endless')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(patch()).toBeTruthy());
    expect(patch().deposit).toBe('20.00');
    // A loan's availability is live, from the calendar: the static hint is cleared.
    expect(patch().availability).toBe('');
    expect(patch()).not.toHaveProperty('type');
  });
});

import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
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
// AddThingPage — field visibility per type / collection config
// ════════════════════════════════════════════════════════════════════════
describe('AddThingPage — field visibility', () => {
  test('GIFT (default): fee hidden, detail fields + gallery shown', async () => {
    const { container } = renderAdd({ collection: { headline: 'Plain', mode: 'PROPRIETARY' } });

    await waitFor(() => expect(container.querySelector('#add-thing-headline')).toBeTruthy());
    // GIFT is a DETAIL_TYPE but not a FEE_TYPE.
    expect(container.querySelector('#add-thing-fee')).toBeNull();
    expect(screen.getByText('Availability')).toBeInTheDocument();
    expect(screen.getByText('Condition')).toBeInTheDocument();
    expect(container.querySelector('#add-thing-location')).toBeTruthy();
    expect(screen.getByText('More photos')).toBeInTheDocument();
    expect(screen.getByText('Thumbnail')).toBeInTheDocument();
  });

  test('SELL (single-type allowlist): pre-selects type, shows fee + detail fields', async () => {
    const { container } = renderAdd({
      collection: { mode: 'PROPRIETARY', allowed_thing_types: ['SELL_THING'] },
    });

    // The single-element allowlist pre-selects SELL_THING, so the fee surfaces.
    await waitFor(() => expect(container.querySelector('#add-thing-fee')).toBeTruthy());
    expect(screen.getByText('Availability')).toBeInTheDocument();
    expect(container.querySelector('#add-thing-location')).toBeTruthy();
  });

  test('single-type allowlist: preselects it and shows its fields', async () => {
    const { container } = renderAdd({
      collection: { mode: 'COMMUNITY', allowed_thing_types: ['LEND_THING'] },
    });

    await waitFor(() => expect(container.querySelector('#add-thing-headline')).toBeTruthy());
    // The Select still renders even when the allowlist leaves one option.
    expect(screen.getByText('Type')).toBeInTheDocument();
    // LEND is a DETAIL_TYPE but not a FEE_TYPE: availability shows, fee hidden.
    expect(container.querySelector('#add-thing-fee')).toBeNull();
    expect(screen.getByText('Availability')).toBeInTheDocument();
  });
});

// ════════════════════════════════════════════════════════════════════════
// AddThingPage — the (i) explaining the thing types (O2)
// ════════════════════════════════════════════════════════════════════════
describe('AddThingPage — type explainer popover', () => {
  test('the (i) opens and describes each type the collection offers', async () => {
    const { container } = renderAdd({ collection: { mode: 'PROPRIETARY' } });

    // Icon-only, accessible name = the panel title.
    const info = await screen.findByRole('button', { name: 'What each type means' });
    fireEvent.click(info);

    // A PROPRIETARY collection offers GIFT (among others) — its description shows.
    expect(await screen.findByText(/whoever claims it keeps it/)).toBeInTheDocument();
    // The bold type label sits next to its description, inside the panel (the same
    // word is also a Select option, so scope the lookup to the popover).
    const panel = within(container.querySelector('#add-thing-type-info'));
    expect(panel.getByText('Gift')).toBeInTheDocument();
  });

  // The panel is built from the already-filtered typeOptions, so a type the
  // collection can't hold is never explained. An allowlist of one leaves one.
  test('does not list a type the collection filtered out', async () => {
    renderAdd({ collection: { mode: 'COMMUNITY', allowed_thing_types: ['SELL_THING'] } });

    fireEvent.click(await screen.findByRole('button', { name: 'What each type means' }));

    // SELL is the only offered type, so its description is present…
    expect(await screen.findByText(/For sale at the price you set/)).toBeInTheDocument();
    // …and GIFT, which the allowlist excludes, is not explained.
    expect(screen.queryByText(/whoever claims it keeps it/)).toBeNull();
  });
});

// ════════════════════════════════════════════════════════════════════════
// AddThingPage — submit payload
// ════════════════════════════════════════════════════════════════════════
describe('AddThingPage — submit', () => {
  test('POSTs to /api/v1/things/ with headline, type and collection_code', async () => {
    const { container } = renderAdd({ collection: { mode: 'PROPRIETARY' } });

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
      expect(body).toMatchObject({
        headline: 'My Gift',
        type: 'GIFT_THING',
        collection_code: 'COL001',
      });
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
      thing: { code: 'THG001', type: 'GIFT_THING', headline: 'Existing Thing', description: '' },
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
      expect(body).toMatchObject({ headline: 'Renamed Thing', type: 'GIFT_THING' });
    });
  });
});

// ════════════════════════════════════════════════════════════════════════
// EditThingPage — a deployment that has narrowed since the thing was offered
// ════════════════════════════════════════════════════════════════════════

describe('EditThingPage — the stored verb stays offered', () => {
  /* A thing offered as a loan, on a deployment that has since stopped handing
     out LEND. The server judges only a **change**, so its owner may still save
     it as it stands — and the type Select has to keep saying so.

     The bug this pins: the option list was filtered against the live `thingType`
     state rather than the stored one, so the moment the owner opened the Select
     and picked something else to compare, LEND stopped counting as "current",
     failed `isOfferable`, and left the list. There was then no way back to the
     verb the thing was actually offered under without reloading. The twin of
     EditCollectionPage's `savedMode`; invisible upstream, where nothing is
     withheld, which is why it needs a test.

     `openTypes()` reads the option list the way a user sees it — the Select
     renders its options only while open, so each read opens it first. */
  const LENT_THING = {
    code: 'THG001',
    type: 'LEND_THING',
    headline: 'Drill',
    tags: [],
    gallery_urls: [],
  };

  function narrowedApi() {
    apiFetch.mockImplementation((url) => {
      if (url.includes('/auth/me/')) {
        return Promise.resolve(
          mockResponse({
            capabilities: {
              collection_modes: ['PROPRIETARY'],
              thing_types: ['GIFT_THING', 'SELL_THING'],
              request_url: null,
            },
          })
        );
      }
      return Promise.resolve(mockResponse(LENT_THING));
    });
  }

  beforeEach(() => {
    // The capabilities cache is module-scope and keyed by account; a fresh code
    // keeps this independent of the tests above, which answer /auth/me/ with {}.
    localStorage.setItem('userCode', `NARROW${Math.random()}`);
    narrowedApi();
  });

  test('it survives the owner trying another verb first', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/things/THG001/edit']}>
        <Routes>
          <Route path="/things/:thingCode/edit" element={<EditThingPage />} />
        </Routes>
      </MemoryRouter>
    );
    await waitFor(() => expect(container.querySelector('#edit-thing-headline')).toBeTruthy());

    // Opens only when closed: the trigger is a toggle, so a helper that clicked
    // unconditionally would shut the list it was about to read.
    const openTypes = () => {
      const trigger = container.querySelector('#edit-thing-type-main-button');
      if (trigger.getAttribute('aria-expanded') !== 'true') fireEvent.click(trigger);
      return [...container.querySelectorAll('[role="option"]')];
    };

    // Offered to begin with, because the thing is offered under it.
    await waitFor(() => expect(openTypes().map((o) => o.textContent)).toContain('Lend'));

    // The owner compares: picks a verb the deployment does allow...
    fireEvent.click(openTypes().find((o) => o.textContent === 'Gift'));

    // ...and can still change their mind. This is the assertion that failed.
    expect(openTypes().map((o) => o.textContent)).toContain('Lend');
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
// Deposit (S6) — LEND/RENT only, and never left ambiguous across an edit
// ════════════════════════════════════════════════════════════════════════

describe('AddThingPage — the deposit field only exists on LEND/RENT', () => {
  test('a GIFT thing never sees a deposit input', async () => {
    const { container } = renderAdd({ collection: { headline: 'Plain', mode: 'PROPRIETARY' } });

    await waitFor(() => expect(container.querySelector('#add-thing-headline')).toBeTruthy());
    expect(container.querySelector('#add-thing-deposit')).toBeNull();
  });

  test('a LEND thing gets the field, with no default and never labelled as part of the price', async () => {
    const { container } = renderAdd({
      collection: { mode: 'COMMUNITY', allowed_thing_types: ['LEND_THING'] },
    });

    await waitFor(() => expect(container.querySelector('#add-thing-deposit')).toBeTruthy());
    // Empty, never pre-filled (DESIGN §6 — no suggested amount).
    expect(container.querySelector('#add-thing-deposit').value).toBe('');
    // A price row for LEND would be wrong regardless — but if it ever appeared,
    // a shared euro icon with no other cue is exactly how "10 + 50" becomes "60 €".
    expect(container.querySelector('#add-thing-fee')).toBeNull();
  });

  test('a RENT thing carries both fields, distinctly labelled', async () => {
    const { container } = renderAdd({
      collection: { mode: 'COMMUNITY', allowed_thing_types: ['RENT_THING'] },
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
      collection: { mode: 'COMMUNITY', allowed_thing_types: ['LEND_THING'] },
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
      expect(JSON.parse(call[1].body)).toMatchObject({ deposit: '50', type: 'LEND_THING' });
    });
  });

  test('leaving it empty never sends the field at all — nothing to clear on a brand-new thing', async () => {
    const { container } = renderAdd({
      collection: { mode: 'COMMUNITY', allowed_thing_types: ['LEND_THING'] },
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
      thing: { code: 'THG001', type: 'LEND_THING', headline: 'Drill', deposit: '50.00' },
    });

    await waitFor(() => expect(container.querySelector('#edit-thing-deposit')).toBeTruthy());
    expect(container.querySelector('#edit-thing-deposit').value).toBe('50');
  });

  test('switching the type away from LEND/RENT clears the deposit in the same PATCH', async () => {
    // The server judges the row that lands (core/serializers/CLAUDE.md): an
    // untouched field keeps its stored value, so this can't be left implicit —
    // the client has to say `deposit: null` itself or the save 400s.
    const { container } = renderEdit({
      thing: { code: 'THG001', type: 'LEND_THING', headline: 'Drill', deposit: '50.00' },
    });
    await waitFor(() => expect(container.querySelector('#edit-thing-deposit')).toBeTruthy());

    fireEvent.click(container.querySelector('#edit-thing-type-main-button'));
    fireEvent.click(await screen.findByRole('option', { name: 'Gift' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      const call = apiFetch.mock.calls.find(
        (c) => c[0] === '/api/v1/things/THG001/' && c[1]?.method === 'PATCH'
      );
      expect(call).toBeTruthy();
      expect(JSON.parse(call[1].body).deposit).toBeNull();
    });
  });

  test('keeping the type as LEND/RENT keeps sending the amount', async () => {
    const { container } = renderEdit({
      thing: { code: 'THG001', type: 'LEND_THING', headline: 'Drill', deposit: '50.00' },
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

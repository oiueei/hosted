import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

window.scrollTo = vi.fn();

const navigate = vi.fn();
vi.mock('react-router', async () => ({
  ...(await vi.importActual('react-router')),
  useNavigate: () => navigate,
}));

// Keep the real `extractApiError` — the 400 tests below feed it real response
// bodies and check the message it pulls out reaches the toast.
vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal()),
  apiFetch: vi.fn(),
  getCsrfToken: () => 'tok',
}));

vi.mock('../hooks/useCollectionLanguage', () => ({ default: vi.fn() }));

import { apiFetch } from '../services/api';
import useCollectionLanguage from '../hooks/useCollectionLanguage';
import EditCollectionPage from './EditCollectionPage';
import { dropHdsStyles } from '../test/dropHdsStyles';

// `collectionForm.test.jsx` covers the shape of this form (which fields are
// visible, which fold into "More options", the pause section). These cover what
// hangs off the save: a save the backend refuses because narrowing the type
// list would orphan things, the notes, the hour rules. The downloads (calendar,
// stats, the whole collection) live in the collection menu now
// (`collectionMenu.test.jsx`); this page offers none.

const COLLECTION = {
  code: 'COL001',
  headline: 'Kitchen Collection',
  description: 'Things from the kitchen',
  mode: 'PROPRIETARY',
  status: 'ACTIVE',
  visibility: 'PRIVATE',
  owner: 'USR001', // matches the userCode set in beforeEach — the viewer is the founder
  allowed_thing_types: ['GIFT_THING'],
  rental_durations: [],
  rental_weekdays: [],
  tags: [],
  is_paused: false,
};

function mockApi({ save = { ok: true } } = {}) {
  apiFetch.mockImplementation((url, opts) => {
    if (opts?.method === 'PATCH') {
      return Promise.resolve({
        ok: save.ok,
        status: save.status ?? (save.ok ? 200 : 400),
        json: async () => save.body ?? {},
      });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => COLLECTION });
  });
}

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/collections/COL001/edit']}>
      <Routes>
        <Route path="/collections/:code/edit" element={<EditCollectionPage />} />
      </Routes>
    </MemoryRouter>
  );

beforeEach(() => {
  dropHdsStyles(); // ByRole queries cost ~10x less without them; see the helper
  localStorage.clear();
  localStorage.setItem('userCode', 'USR001');
  vi.clearAllMocks();
});
afterEach(() => vi.restoreAllMocks());

describe('EditCollectionPage — saving', () => {
  test('a successful save returns to the collection', async () => {
    mockApi();
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/collections/COL001'));
  });

  test('a narrowing that would orphan things shows which types, not "Error saving"', async () => {
    // The backend refuses to drop a type while things of that type still live
    // here, and its message names them. Swallowing it for a generic error would
    // leave the owner with a save that fails and nothing to act on — they can't
    // guess which of four types is the blocker.
    mockApi({
      save: {
        ok: false,
        status: 400,
        body: { non_field_errors: ['Remove the LEND_THING items first: 3 would be orphaned.'] },
      },
    });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');
    navigate.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(
      await screen.findByText('Remove the LEND_THING items first: 3 would be orphaned.')
    ).toBeInTheDocument();
    expect(screen.queryByText('Error saving.')).toBeNull();
    expect(navigate).not.toHaveBeenCalled();
  });

  test('a 400 with a DRF `detail` is surfaced the same way', async () => {
    mockApi({ save: { ok: false, status: 400, body: { detail: 'That headline is too long.' } } });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('That headline is too long.')).toBeInTheDocument();
  });

  test('a 400 with nothing readable in it still says something', async () => {
    mockApi({ save: { ok: false, status: 400, body: {} } });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Error saving.')).toBeInTheDocument();
  });

  test('a rate-limited save says "too many", not "error"', async () => {
    mockApi({ save: { ok: false, status: 429 } });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText(/[Tt]oo many/)).toBeInTheDocument();
  });

  test('a space booked by the day saves its day rules, and none of the hourly ones', async () => {
    // Since the DAY/HOUR switch, the day branch of the save body — the one
    // every reservations collection that predates HOUR is on — was never sent
    // by any test: an owner's new day cap could stop reaching the server and
    // the form would still say it was saved.
    const byTheDay = {
      ...COLLECTION,
      allowed_thing_types: ['RESERVE_THING'],
      reservation_unit: 'DAY',
      reservation_max_days: 3,
    };
    apiFetch.mockImplementation((url, opts) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: async () => (opts?.method === 'PATCH' ? {} : byTheDay),
      })
    );
    const { container } = renderPage();
    await screen.findByDisplayValue('Kitchen Collection');
    fireEvent.click(screen.getByRole('button', { name: 'More options' }));
    const maxDays = container.querySelector('#edit-collection-reservation-max-days');
    expect(maxDays).toHaveValue(3);
    fireEvent.change(maxDays, { target: { value: '5' } });
    fireEvent.blur(maxDays);

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/collections/COL001'));
    const [, patch] = apiFetch.mock.calls.find(([, o]) => o?.method === 'PATCH');
    const body = JSON.parse(patch.body);
    expect(body.reservation_unit).toBe('DAY');
    expect(body.reservation_max_days).toBe(5);
    for (const hourly of ['opening_hours', 'reservation_min_minutes', 'reservation_max_minutes']) {
      expect(body).not.toHaveProperty(hourly);
    }
  });
});

describe('EditCollectionPage — the delete button', () => {
  // Save, pause, stats and export carry no client-side gate at all — the
  // server has always been the only thing that decides, and a co-owner
  // reaching this page now succeeds at every one of them exactly as the
  // founder would. Delete stays the one exception: never a co-owner power,
  // so it isn't worth showing a control the server would 403.
  test('the founder sees it', async () => {
    mockApi();
    renderPage();

    expect(await screen.findByRole('button', { name: 'Delete' })).toBeInTheDocument();
  });

  test('a co-owner reaching this page does not see it', async () => {
    apiFetch.mockImplementation(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ ...COLLECTION, owner: 'FOUNDER1' }),
      })
    );
    renderPage();

    await screen.findByDisplayValue('Kitchen Collection');
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
  });
});

describe('EditCollectionPage — no downloads', () => {
  // The calendar, the stats and the whole-collection export left the foot of
  // this page for the collection menu, with the two notes that
  // went with them. A page that offered them again would be a second place to
  // run the group's data from, which is what the move was for.
  test('the page offers no download, and asks for no file', async () => {
    mockApi();
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    expect(screen.queryByRole('button', { name: /download/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /download/i })).not.toBeInTheDocument();
    const asked = apiFetch.mock.calls.map(([url]) => url);
    expect(asked.filter((url) => /\/(stats|export|calendar-export)\//.test(url))).toEqual([]);
  });
});

describe('EditCollectionPage — the deposit policy', () => {
  test('a stored policy pre-fills the field, once "More options" is open', async () => {
    mockApi();
    apiFetch.mockImplementation((url, opts) => {
      if (opts?.method === 'PATCH')
        return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
      if (url.includes('/stats/') || url.includes('/export/')) {
        return Promise.resolve({ ok: true, status: 200, blob: async () => new Blob(['x']) });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ ...COLLECTION, deposit_policy: '50 €, back when it comes home' }),
      });
    });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));

    expect(screen.getByLabelText(/deposit policy/i).value).toBe('50 €, back when it comes home');
  });

  test('an edited policy reaches the PATCH body', async () => {
    mockApi();
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));
    fireEvent.change(screen.getByLabelText(/deposit policy/i), {
      target: { value: 'No deposits in this group.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      const call = apiFetch.mock.calls.find((c) => c[1]?.method === 'PATCH');
      expect(call).toBeTruthy();
      expect(JSON.parse(call[1].body).deposit_policy).toBe('No deposits in this group.');
    });
  });
});

describe('EditCollectionPage — the request-page note', () => {
  test('a stored note pre-fills the field, once "More options" is open', async () => {
    mockApi();
    apiFetch.mockImplementation((url, opts) => {
      if (opts?.method === 'PATCH')
        return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
      if (url.includes('/stats/') || url.includes('/export/')) {
        return Promise.resolve({ ok: true, status: 200, blob: async () => new Blob(['x']) });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ ...COLLECTION, request_info: 'Bring photo ID.' }),
      });
    });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));

    expect(screen.getByLabelText(/note shown before someone asks/i).value).toBe('Bring photo ID.');
  });

  test('an edited note reaches the PATCH body', async () => {
    mockApi();
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));
    fireEvent.change(screen.getByLabelText(/note shown before someone asks/i), {
      target: { value: 'Pickup is Tuesdays only.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      const call = apiFetch.mock.calls.find((c) => c[1]?.method === 'PATCH');
      expect(call).toBeTruthy();
      expect(JSON.parse(call[1].body).request_info).toBe('Pickup is Tuesdays only.');
    });
  });

  test('the counter reflects the 512-per-language limit, not the old 256', async () => {
    mockApi();
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));
    fireEvent.change(screen.getByLabelText(/note shown before someone asks/i), {
      target: { value: 'Bring ID.' },
    });

    expect(screen.getByText('9/512')).toBeInTheDocument();
  });

  test('typing past 512 shows the limit error right away, with no submit needed', async () => {
    mockApi();
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));
    const field = screen.getByLabelText(/note shown before someone asks/i);
    fireEvent.change(field, { target: { value: 'x'.repeat(513) } });

    expect(screen.getByText('Maximum 512 characters per language.')).toBeInTheDocument();
    // The field references the error via aria-describedby, so a screen
    // reader announces it without waiting for a submit attempt.
    expect(field.getAttribute('aria-describedby')).toContain('edit-collection-request-info-error');
  });
});

describe('EditCollectionPage — the email note', () => {
  test('a stored note pre-fills the field, once "More options" is open', async () => {
    mockApi();
    apiFetch.mockImplementation((url, opts) => {
      if (opts?.method === 'PATCH')
        return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
      if (url.includes('/stats/') || url.includes('/export/')) {
        return Promise.resolve({ ok: true, status: 200, blob: async () => new Blob(['x']) });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ ...COLLECTION, email_note: 'We confirm within 48h.' }),
      });
    });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));

    expect(screen.getByLabelText(/note in the emails after someone asks/i).value).toBe(
      'We confirm within 48h.'
    );
  });

  test('the loaded note can be mailed to the curator as a test, from right under it', async () => {
    // Written blind otherwise: it only reaches requesters, and a curator can't
    // request their own things (EmailNoteTest.test.jsx covers the button).
    apiFetch.mockImplementation((url, opts) => {
      if (opts?.method === 'POST') {
        return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ ...COLLECTION, email_note: 'We confirm within 48h.' }),
      });
    });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');
    fireEvent.click(screen.getByRole('button', { name: 'More options' }));

    fireEvent.click(screen.getByRole('button', { name: 'Send me a test email' }));

    expect(await screen.findByText(/Sent to your inbox/)).toBeInTheDocument();
    const post = apiFetch.mock.calls.find(([, o]) => o?.method === 'POST');
    expect(post[0]).toBe('/api/v1/collections/COL001/email-note/test/');
    expect(JSON.parse(post[1].body)).toEqual({ email_note: 'We confirm within 48h.' });
  });

  test('an edited note reaches the PATCH body, trimmed', async () => {
    mockApi();
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));
    fireEvent.change(screen.getByLabelText(/note in the emails after someone asks/i), {
      target: { value: '  The space is on floor 2.  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      const call = apiFetch.mock.calls.find((c) => c[1]?.method === 'PATCH');
      expect(call).toBeTruthy();
      expect(JSON.parse(call[1].body).email_note).toBe('The space is on floor 2.');
    });
  });

  test('the counter reflects the same 512-per-language limit as the request note', async () => {
    mockApi();
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));
    fireEvent.change(screen.getByLabelText(/note in the emails after someone asks/i), {
      target: { value: 'Floor 2.' },
    });

    expect(screen.getByText('8/512')).toBeInTheDocument();
  });

  test('typing past 512 shows the limit error right away, with no submit needed', async () => {
    mockApi();
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));
    const field = screen.getByLabelText(/note in the emails after someone asks/i);
    fireEvent.change(field, { target: { value: 'x'.repeat(513) } });

    expect(screen.getByText('Maximum 512 characters per language.')).toBeInTheDocument();
    expect(field.getAttribute('aria-describedby')).toContain('edit-collection-email-note-error');
  });
});

describe('EditCollectionPage — a deployment that has narrowed since', () => {
  /* A collection opened while COMMUNITY was on offer, on a deployment that has
     since stopped handing it out. The server judges only a **change**, so this
     owner may still save it as it stands — and the form has to keep saying so.

     The bug this pins: the filter keyed on the live `mode` state rather than
     the stored one, so the moment the owner clicked the other radio to compare,
     COMMUNITY stopped being "current", failed `isOfferable`, and unmounted.
     There was then no way back to the mode the collection was actually in
     without reloading the page — a form that had quietly become unable to
     express the row it was editing. Invisible upstream, where nothing is
     withheld, which is exactly why it needs a test. */
  const COMMUNITY_COLLECTION = { ...COLLECTION, mode: 'COMMUNITY' };

  function mockNarrowedApi() {
    apiFetch.mockImplementation((url) => {
      if (url.includes('/auth/me/')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            capabilities: {
              collection_modes: ['PROPRIETARY'],
              thing_types: ['GIFT_THING', 'SELL_THING'],
              request_url: 'https://example.org/request-access/',
            },
          }),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => COMMUNITY_COLLECTION });
    });
  }

  beforeEach(() => {
    // The capabilities cache is module-scope and keyed by account; a fresh code
    // keeps these independent of the tests above without a reset export.
    localStorage.setItem('userCode', `NARROW${Math.random()}`);
    mockNarrowedApi();
  });

  test('the stored mode stays on offer after the owner tries the other one', async () => {
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    const community = () => screen.queryByRole('radio', { name: /community/i });
    // It is offered to begin with, because the collection is in it.
    await waitFor(() => expect(community()).not.toBeNull());

    // The owner compares: clicks the mode the deployment does allow...
    fireEvent.click(screen.getByRole('radio', { name: /just mine|proprietary/i }));

    // ...and can still change their mind. This is the assertion that failed.
    expect(community()).not.toBeNull();
    fireEvent.click(community());
    expect(community()).toBeChecked();
  });
});

describe('EditCollectionPage — useCollectionLanguage gets the saved value, never the draft', () => {
  // The page holds two things called "language": `savedLanguage` (the stored
  // value, as loaded) and `language` (the form's live-edited draft, which
  // defaults to the browser's own language the moment the field is blank).
  // Feeding the draft into `useCollectionLanguage` would flip this whole
  // settings form's own UI language the instant the owner merely tries an
  // option in the dropdown, before saving anything — the exact regression
  // this test exists to catch (found in review, 2026-09-15).
  test('trying a different language in the dropdown does not change what the hook is called with', async () => {
    apiFetch.mockImplementation((url) => {
      if (url === '/api/v1/collections/COL001/') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ ...COLLECTION, language: 'ca' }),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
    });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    const SAVED_TEXTS = ['Kitchen Collection', 'Things from the kitchen'];
    await waitFor(() => expect(useCollectionLanguage).toHaveBeenLastCalledWith('ca', SAVED_TEXTS));

    // The owner's texts as saved, not as being typed: rewriting the headline
    // (into another language, say) must not move the form's own language.
    fireEvent.change(screen.getByDisplayValue('Kitchen Collection'), {
      target: { value: '{"es": "Cocina", "en": "Kitchen"}' },
    });
    expect(useCollectionLanguage).toHaveBeenLastCalledWith('ca', SAVED_TEXTS);

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));
    const languageCombobox = await screen.findByRole('combobox', {
      name: /Language of the group messages/,
    });
    fireEvent.click(languageCombobox);
    fireEvent.click(await screen.findByRole('option', { name: 'Español' }));

    // The dropdown itself did change — this isn't a no-op click...
    await waitFor(() => expect(languageCombobox).toHaveTextContent('Español'));
    // ...but the hook must still see the collection's actual saved language.
    expect(useCollectionLanguage).toHaveBeenLastCalledWith('ca', SAVED_TEXTS);
  });
});

describe('EditCollectionPage — an unparseable opening-hours draft blocks Save', () => {
  // OpeningHoursField keeps the last good value while its draft doesn't parse.
  // Save used to send that stale value and navigate away, taking the inline
  // error with it: an owner whose paste had a trailing comma believed a new
  // schedule was saved when the old one was (found in review, 2026-09-18).
  const HOURLY = {
    ...COLLECTION,
    allowed_thing_types: ['RESERVE_THING'],
    reservation_unit: 'HOUR',
    opening_hours: { 0: [['10:00', '14:00']] },
  };

  function mockHourly() {
    apiFetch.mockImplementation((url, opts) => {
      if (opts?.method === 'PATCH')
        return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
      return Promise.resolve({ ok: true, status: 200, json: async () => HOURLY });
    });
  }

  const patchCalls = () => apiFetch.mock.calls.filter((c) => c[1]?.method === 'PATCH');

  function typeOpeningHours(value) {
    const field = screen.getByLabelText('Weekly opening hours');
    fireEvent.change(field, { target: { value } });
    fireEvent.blur(field);
  }

  async function openForm() {
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');
    fireEvent.click(screen.getByRole('button', { name: 'More options' }));
  }

  test('Save sends nothing, stays put, and says why', async () => {
    mockHourly();
    await openForm();
    typeOpeningHours('{"0": [["10:00","14:00"]],}');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText(/Nothing was saved: the weekly opening hours/)).toBeVisible();
    expect(patchCalls()).toHaveLength(0);
    expect(navigate).not.toHaveBeenCalled();
  });

  test('folding "More options" away does not lift the refusal', async () => {
    // HDS keeps a closed Accordion's content mounted (display: none), so the
    // field's refusal survives the owner collapsing the section before Save.
    // If an HDS upgrade ever unmounted it instead, the field's unmount cleanup
    // would report "valid" and the silent stale save would be back.
    mockHourly();
    await openForm();
    typeOpeningHours('{"0": [["10:00","14:00"]],}');
    fireEvent.click(screen.getByRole('button', { name: 'More options' }));
    expect(screen.getByLabelText('Weekly opening hours')).not.toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText(/Nothing was saved: the weekly opening hours/)).toBeVisible();
    expect(patchCalls()).toHaveLength(0);
  });

  test('fixing the draft lets the corrected schedule through', async () => {
    mockHourly();
    await openForm();
    typeOpeningHours('{"0": [["10:00","14:00"]],}');
    typeOpeningHours('{"0": [["09:00","13:00"]]}');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(patchCalls()).toHaveLength(1));
    expect(JSON.parse(patchCalls()[0][1].body).opening_hours).toEqual({
      0: [['09:00', '13:00']],
    });
  });

  test('leaving "By hour" and coming back drops the refusal with the broken draft', async () => {
    // Switching to DAY unmounts the field, and coming back remounts it showing
    // the last good schedule with no error. A refusal that outlived the draft
    // it was about would block a Save with nothing on screen to fix.
    mockHourly();
    await openForm();
    typeOpeningHours('not json');
    fireEvent.click(screen.getByRole('radio', { name: 'By day' }));
    fireEvent.click(screen.getByRole('radio', { name: 'By hour' }));
    expect(screen.getByLabelText('Weekly opening hours')).toHaveValue(
      JSON.stringify(HOURLY.opening_hours)
    );

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(patchCalls()).toHaveLength(1));
    expect(JSON.parse(patchCalls()[0][1].body).opening_hours).toEqual(HOURLY.opening_hours);
  });
});

/**
 * Pausing is what stops every new request in the group, and resuming is what lets
 * them in again: both are their own PATCH of `pause_message`, apart from Save.
 * `collectionForm.test.jsx` pins which controls show in each state; these press them.
 */
describe('EditCollectionPage — pausing and resuming', () => {
  const pauseCalls = () =>
    apiFetch.mock.calls.filter(
      (c) => c[1]?.method === 'PATCH' && 'pause_message' in JSON.parse(c[1].body)
    );

  function mockPausable({ collection = COLLECTION, patch } = {}) {
    apiFetch.mockImplementation((url, opts) => {
      if (opts?.method === 'PATCH') return patch();
      return Promise.resolve({ ok: true, status: 200, json: async () => collection });
    });
  }

  const ok = () => Promise.resolve({ ok: true, status: 200, json: async () => ({}) });

  test('nothing can be paused without a message for the members', async () => {
    mockPausable({ patch: ok });
    renderPage();
    const pause = await screen.findByRole('button', { name: 'Pause collection' });

    expect(pause).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Message to members'), { target: { value: '   ' } });
    expect(pause).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Message to members'), {
      target: { value: 'Back in a week' },
    });
    expect(pause).toBeEnabled();
  });

  test('pausing sends the message alone, trimmed, and shows it as the members will', async () => {
    mockPausable({ patch: ok });
    renderPage();
    fireEvent.change(await screen.findByLabelText('Message to members'), {
      target: { value: '  Back in a week  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Pause collection' }));

    expect(await screen.findByText('Collection paused.')).toBeInTheDocument();
    expect(pauseCalls()).toHaveLength(1);
    const [url, opts] = pauseCalls()[0];
    expect(url).toBe('/api/v1/collections/COL001/');
    // Only the pause: an unsaved edit elsewhere on the form must not ride along.
    expect(JSON.parse(opts.body)).toEqual({ pause_message: 'Back in a week' });
    expect(screen.getByText('Back in a week').tagName).toBe('BLOCKQUOTE');
    expect(screen.getByRole('button', { name: 'Resume collection' })).toBeEnabled();
    expect(screen.queryByLabelText('Message to members')).toBeNull();
  });

  test('resuming clears the message and offers an empty field again', async () => {
    mockPausable({
      collection: { ...COLLECTION, is_paused: true, pause_message: 'Back in a week' },
      patch: ok,
    });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Resume collection' }));

    expect(await screen.findByText('Collection resumed.')).toBeInTheDocument();
    expect(JSON.parse(pauseCalls()[0][1].body)).toEqual({ pause_message: '' });
    expect(screen.getByLabelText('Message to members')).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Pause collection' })).toBeDisabled();
  });

  test.each([
    [
      'a refusal',
      () => Promise.resolve({ ok: false, status: 400, json: async () => ({}) }),
      'Error',
    ],
    ['a dropped connection', () => Promise.reject(new TypeError('offline')), 'Connection error.'],
  ])('%s leaves the group open and says so', async (_label, patch, message) => {
    mockPausable({ patch });
    renderPage();
    fireEvent.change(await screen.findByLabelText('Message to members'), {
      target: { value: 'Back in a week' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Pause collection' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(screen.queryByText('Collection paused.')).toBeNull();
    expect(screen.getByRole('button', { name: 'Pause collection' })).toBeEnabled();
    expect(screen.getByLabelText('Message to members')).toHaveValue('Back in a week');
  });
});

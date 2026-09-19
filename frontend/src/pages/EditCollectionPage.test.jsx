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

// `collectionForm.test.jsx` covers the shape of this form (which fields are
// visible, which fold into "More options", the pause section). These cover the
// two owner tools hanging off the bottom of it, both of which fail in ways the
// owner has to be able to read: a save the backend refuses because narrowing
// the type list would orphan things, and the stats download.

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

function mockApi({
  save = { ok: true },
  stats = { ok: true },
  collectionExport = { ok: true },
  calendar = { ok: true, count: '1' },
} = {}) {
  apiFetch.mockImplementation((url, opts) => {
    if (opts?.method === 'PATCH') {
      return Promise.resolve({
        ok: save.ok,
        status: save.status ?? (save.ok ? 200 : 400),
        json: async () => save.body ?? {},
      });
    }
    if (url.includes('/calendar-export/')) {
      return Promise.resolve({
        ok: calendar.ok,
        status: calendar.status ?? (calendar.ok ? 200 : 500),
        headers: { get: (name) => (name === 'X-Calendar-Events' ? calendar.count : null) },
        blob: async () => new Blob(['Subject,Start Date\n'], { type: 'text/csv' }),
      });
    }
    if (url.includes('/stats/')) {
      return Promise.resolve({
        ok: stats.ok,
        status: stats.ok ? 200 : 500,
        blob: async () => new Blob(['metric,value\nmembers,3\n'], { type: 'text/csv' }),
      });
    }
    if (url.includes('/export/')) {
      return Promise.resolve({
        ok: collectionExport.ok,
        status: collectionExport.status ?? (collectionExport.ok ? 200 : 500),
        headers: {
          get: (name) =>
            name === 'Content-Disposition'
              ? 'attachment; filename="oiueei-COL001-2026-08-21.json"'
              : null,
        },
        blob: async () => new Blob(['{}'], { type: 'application/json' }),
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
  localStorage.clear();
  localStorage.setItem('userCode', 'USR001');
  vi.clearAllMocks();
  // jsdom implements neither, and the download path calls both.
  URL.createObjectURL = vi.fn(() => 'blob:fake');
  URL.revokeObjectURL = vi.fn();
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

describe('EditCollectionPage — the stats download', () => {
  test('downloading names the file after the collection', async () => {
    mockApi();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'Download stats (CSV)' }));

    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(URL.createObjectURL).toHaveBeenCalled();
    // Released again: an owner may download this repeatedly from one page load,
    // and every un-revoked blob URL pins its data for the life of the document.
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:fake'));
  });

  test('a failed download says so instead of silently doing nothing', async () => {
    // A click that produces no file and no message reads as a broken button.
    mockApi({ stats: { ok: false } });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'Download stats (CSV)' }));

    expect(await screen.findByText("Couldn't download the stats.")).toBeInTheDocument();
  });

  test('the error clears when a later download succeeds', async () => {
    let failing = true;
    apiFetch.mockImplementation((url) => {
      if (url.includes('/stats/')) {
        return Promise.resolve({
          ok: !failing,
          status: failing ? 500 : 200,
          blob: async () => new Blob(['metric,value\n']),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => COLLECTION });
    });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'Download stats (CSV)' }));
    await screen.findByText("Couldn't download the stats.");

    failing = false;
    fireEvent.click(screen.getByRole('button', { name: 'Download stats (CSV)' }));

    await waitFor(() => expect(screen.queryByText("Couldn't download the stats.")).toBeNull());
  });
});

describe('EditCollectionPage — the deposit policy (S6)', () => {
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

    expect(screen.getByLabelText(/note for the request page/i).value).toBe('Bring photo ID.');
  });

  test('an edited note reaches the PATCH body', async () => {
    mockApi();
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));
    fireEvent.change(screen.getByLabelText(/note for the request page/i), {
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
    fireEvent.change(screen.getByLabelText(/note for the request page/i), {
      target: { value: 'Bring ID.' },
    });

    expect(screen.getByText('9/512')).toBeInTheDocument();
  });

  test('typing past 512 shows the limit error right away, with no submit needed', async () => {
    mockApi();
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));
    const field = screen.getByLabelText(/note for the request page/i);
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

    expect(screen.getByLabelText(/note in the request emails/i).value).toBe(
      'We confirm within 48h.'
    );
  });

  test('an edited note reaches the PATCH body, trimmed', async () => {
    mockApi();
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));
    fireEvent.change(screen.getByLabelText(/note in the request emails/i), {
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
    fireEvent.change(screen.getByLabelText(/note in the request emails/i), {
      target: { value: 'Floor 2.' },
    });

    expect(screen.getByText('8/512')).toBeInTheDocument();
  });

  test('typing past 512 shows the limit error right away, with no submit needed', async () => {
    mockApi();
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: 'More options' }));
    const field = screen.getByLabelText(/note in the request emails/i);
    fireEvent.change(field, { target: { value: 'x'.repeat(513) } });

    expect(screen.getByText('Maximum 512 characters per language.')).toBeInTheDocument();
    expect(field.getAttribute('aria-describedby')).toContain('edit-collection-email-note-error');
  });
});

describe('EditCollectionPage — the collection export', () => {
  test('downloading names the file after the one the server set, not a guess', async () => {
    mockApi();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: /download the whole collection/i }));

    await waitFor(() => expect(click).toHaveBeenCalled());
    const anchor = click.mock.contexts[0];
    expect(anchor.download).toBe('oiueei-COL001-2026-08-21.json');
    expect(URL.createObjectURL).toHaveBeenCalled();
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:fake'));
  });

  test("the warning that it carries other members' data is always on the page", async () => {
    mockApi();
    renderPage();

    expect(await screen.findByText(/carries other people's data/i)).toBeInTheDocument();
  });

  test('a 429 says "too many attempts", the same message every rate-limited action uses', async () => {
    mockApi({ collectionExport: { ok: false, status: 429 } });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: /download the whole collection/i }));

    expect(
      await screen.findByText('Too many attempts — please wait a moment and try again.')
    ).toBeInTheDocument();
  });

  test('any other failure says so instead of doing nothing', async () => {
    mockApi({ collectionExport: { ok: false, status: 500 } });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', { name: /download the whole collection/i }));

    expect(
      await screen.findByText("Couldn't build the export. Please try again in a moment.")
    ).toBeInTheDocument();
  });
});

describe('EditCollectionPage — the calendar export', () => {
  const button = { name: /download reservations for your calendar/i };

  test('it POSTs to the calendar-export endpoint and downloads the file', async () => {
    mockApi({ calendar: { ok: true, count: '2' } });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', button));

    await waitFor(() => expect(click).toHaveBeenCalled());
    const call = apiFetch.mock.calls.find((c) => c[0].includes('/calendar-export/'));
    expect(call[0]).toBe('/api/v1/collections/COL001/calendar-export/');
    expect(call[1].method).toBe('POST');
    expect(click.mock.contexts[0].download).toBe('COL001-calendar.csv');
    expect(await screen.findByText('2 new event(s) — check your downloads.')).toBeInTheDocument();
  });

  test('nothing new: no download, and it says so', async () => {
    mockApi({ calendar: { ok: true, count: '0' } });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', button));

    expect(await screen.findByText('Nothing new since your last download.')).toBeInTheDocument();
    expect(click).not.toHaveBeenCalled();
  });

  test('the "only the new ones" promise is stated on the page before any click', async () => {
    mockApi();
    renderPage();

    expect(
      await screen.findByText(/only the ones added since your last download/i)
    ).toBeInTheDocument();
  });

  test('a 429 says "too many attempts", like every other rate-limited action', async () => {
    mockApi({ calendar: { ok: false, status: 429 } });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', button));

    expect(
      await screen.findByText('Too many attempts — please wait a moment and try again.')
    ).toBeInTheDocument();
  });

  test('any other failure is shown, not swallowed', async () => {
    mockApi({ calendar: { ok: false, status: 500 } });
    renderPage();
    await screen.findByDisplayValue('Kitchen Collection');

    fireEvent.click(screen.getByRole('button', button));

    expect(
      await screen.findByText("Couldn't build the calendar file. Please try again in a moment.")
    ).toBeInTheDocument();
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

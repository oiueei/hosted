import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';
import { axe, toHaveNoViolations } from 'jest-axe';

expect.extend(toHaveNoViolations);

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import i18n from '../i18n';
import InboxNotifications from '../components/InboxNotifications';
import { switchLanguage } from './settle';

// What only informs folds into one card past three; what asks for an action stays a
// card of its own, as it was.

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

const broadcast = (n) => ({
  code: `BRD${n}`,
  type: 'BROADCAST',
  payload: { message: `News ${n}`, collection_headline: 'Tools', collection_code: 'COL001' },
  created: '2026-10-02T10:00:00Z',
});
const question = {
  code: 'FAQ001',
  type: 'FAQ_QUESTION',
  payload: {
    thing_headline: 'A ladder',
    questioner_name: 'Lili',
    thing_code: 'THG099',
    collection_code: 'COL001',
  },
  created: '2026-10-02T09:00:00Z',
};

const setApi = (inbox) =>
  apiFetch.mockImplementation((url, options) =>
    options?.method === 'DELETE' ? ok(null) : ok(inbox)
  );

const renderInbox = (props) =>
  render(
    <MemoryRouter>
      <InboxNotifications {...props} />
    </MemoryRouter>
  );

const FIVE = [1, 2, 3, 4, 5].map(broadcast);

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(async () => {
  await switchLanguage(i18n, 'en');
  localStorage.removeItem('i18nextLng');
  localStorage.removeItem('theeemeColors');
});

describe('five updates and one question', () => {
  test('the question is a card of its own and the five updates are one folded card', async () => {
    setApi([question, ...FIVE]);
    renderInbox();

    expect(await screen.findByText('5 updates')).toBeInTheDocument();
    expect(screen.getByText(/A ladder/)).toBeInTheDocument();
    expect(screen.queryByText(/News 1/)).not.toBeInTheDocument();
  });

  test('Show opens them one by one and Hide folds them again', async () => {
    setApi(FIVE);
    renderInbox();
    const show = await screen.findByRole('button', { name: 'Show' });
    expect(show).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(show);

    for (const n of [1, 2, 3, 4, 5])
      expect(screen.getByText(new RegExp(`News ${n}`))).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Hide' }));
    expect(screen.queryByText(/News 1/)).not.toBeInTheDocument();
  });

  const deletes = () => apiFetch.mock.calls.filter(([, o]) => o?.method === 'DELETE');
  // The trigger and, once the panel is open, the confirm button share the label;
  // the confirm is the one inside the panel.
  const openConfirm = async () => {
    fireEvent.click(await screen.findByRole('button', { name: 'Dismiss all' }));
    return within(screen.getByText('Dismiss all 5?').closest('.thing-report-confirm'));
  };

  test('one press on Dismiss all deletes nothing: it asks first, and says what happens', async () => {
    setApi([question, ...FIVE]);
    renderInbox();
    const panel = await openConfirm();

    expect(panel.getByText(/can't be brought back/)).toBeInTheDocument();
    expect(deletes()).toHaveLength(0);
    expect(screen.getByText('5 updates')).toBeInTheDocument();
  });

  test('confirming takes the updates in one call and leaves the question', async () => {
    setApi([question, ...FIVE]);
    renderInbox();
    const panel = await openConfirm();
    fireEvent.click(panel.getByRole('button', { name: 'Dismiss all' }));

    await waitFor(() => expect(screen.queryByText('5 updates')).not.toBeInTheDocument());
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/inbox/?group=info', { method: 'DELETE' });
    expect(deletes()).toHaveLength(1);
    expect(screen.getByText(/A ladder/)).toBeInTheDocument();
  });

  test('the confirm button is the primary of the reader’s theeeme', async () => {
    localStorage.setItem(
      'theeemeColors',
      JSON.stringify({
        color_01: 'metro',
        color_02: 'white',
        color_03: 'fog',
        color_04: 'black',
        color_06: 'white',
      })
    );
    setApi([question, ...FIVE]);
    renderInbox();
    const panel = await openConfirm();

    const confirm = panel.getByRole('button', { name: 'Dismiss all' });
    expect(confirm.style.getPropertyValue('--background-color')).toBe('var(--color-metro)');
  });

  test('cancelling leaves every update where it was', async () => {
    setApi([question, ...FIVE]);
    renderInbox();
    const panel = await openConfirm();
    fireEvent.click(panel.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByText('Dismiss all 5?')).not.toBeInTheDocument();
    expect(deletes()).toHaveLength(0);
    expect(screen.getByText('5 updates')).toBeInTheDocument();
  });

  test('on a collection’s page it asks for that collection only', async () => {
    setApi(FIVE);
    renderInbox({ collection: 'COL001' });
    const panel = await openConfirm();
    fireEvent.click(panel.getByRole('button', { name: 'Dismiss all' }));

    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith('/api/v1/inbox/?group=info&collection=COL001', {
        method: 'DELETE',
      })
    );
  });

  test('Hide names the notices it folds away: every id it controls is an informative notice', async () => {
    setApi([question, ...FIVE]);
    const { container } = renderInbox();
    fireEvent.click(await screen.findByRole('button', { name: 'Show' }));

    const ids = screen
      .getByRole('button', { name: 'Hide' })
      .getAttribute('aria-controls')
      .split(' ');
    expect(ids).toHaveLength(5);
    for (const id of ids) {
      const notice = container.querySelector(`#${id}`);
      expect(notice, id).not.toBeNull();
      expect(notice).toHaveTextContent(/News \d/);
    }
    // The question is not folded, so it is not among them.
    expect(ids).not.toContain('inbox-notice-FAQ001');
    expect(container.querySelector('#inbox-notice-FAQ001')).not.toBeNull();
  });

  test('closed, Show controls nothing: its notices are not in the page to point at', async () => {
    setApi([question, ...FIVE]);
    renderInbox();

    expect(await screen.findByRole('button', { name: 'Show' })).not.toHaveAttribute(
      'aria-controls'
    );
  });

  test('has no accessibility violation with the card open', async () => {
    setApi(FIVE);
    const { container } = renderInbox();
    fireEvent.click(await screen.findByRole('button', { name: 'Show' }));

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe('three updates or fewer', () => {
  test('are shown as they always were, with no folded card', async () => {
    setApi([1, 2, 3].map(broadcast));
    renderInbox();

    expect(await screen.findByText(/News 3/)).toBeInTheDocument();
    expect(screen.queryByText(/updates/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Dismiss all' })).not.toBeInTheDocument();
  });

  test('questions never fold, however many', async () => {
    setApi([1, 2, 3, 4, 5].map((n) => ({ ...question, code: `FAQ00${n}` })));
    renderInbox();

    expect((await screen.findAllByText(/A ladder/)).length).toBe(5);
    expect(screen.queryByText(/updates/)).not.toBeInTheDocument();
  });
});

describe('in the reader’s language', () => {
  test.each([
    ['es', '5 novedades', 'Ver', 'Descartar todas'],
    ['ca', '5 novetats', 'Veure', 'Descarta-les totes'],
  ])('%s', async (language, label, show, dismissAll) => {
    await switchLanguage(i18n, language);
    setApi(FIVE);
    renderInbox();

    expect(await screen.findByText(label)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: show })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: dismissAll })).toBeInTheDocument();
  });
});

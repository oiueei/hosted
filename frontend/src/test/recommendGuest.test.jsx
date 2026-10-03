import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: () => 'tok',
  extractApiError: () => null,
}));

import { apiFetch } from '../services/api';
import RecommendGuest from '../components/RecommendGuest';

// A member recommending someone. The thing that must never blur: they have not
// invited anybody. The owner decides, and until they do, the person named here
// is not contacted and does not know they were suggested. A member who walked
// away thinking an invitation had gone out would be misled by us.
// The component paints the form alone: the button that opens it is the page's
// (`CollectionPage`'s member row, `collectionPage` tests), so here it is open.
function renderRecommend(onClose = vi.fn(), props = {}) {
  return render(
    <MemoryRouter>
      <RecommendGuest
        id="recommend-box"
        collectionCode="COL001"
        ownerName="Lala"
        onClose={onClose}
        {...props}
      />
    </MemoryRouter>
  );
}

describe('RecommendGuest', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });
  afterEach(() => vi.restoreAllMocks());

  test('the form says the owner decides before anything is sent', async () => {
    renderRecommend();

    expect(screen.getByText(/Lala decides/)).toBeInTheDocument();
    expect(screen.getByText(/nothing is sent to them until they say yes/i)).toBeInTheDocument();
  });

  test('the owner name is interpolated into the note field label, not left as {{owner}}', () => {
    // recommend.noteLabel carries {{owner}} in all three locales; the label read
    // "Anything {{owner}} should know?" verbatim because the t() call was missing
    // the param that the helper text right beside it already passed.
    renderRecommend();

    const noteField = screen.getByLabelText(/Anything Lala should know/i);
    expect(noteField).toBeInTheDocument();
    expect(screen.queryByText(/\{\{owner\}\}/)).toBeNull();
  });

  test('recommending posts the email and the note to the propose endpoint', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    renderRecommend();

    fireEvent.change(screen.getByLabelText(/Their email/i), {
      target: { value: 'lili@example.com' },
    });
    fireEvent.change(screen.getByLabelText(/should know/i), {
      target: { value: 'my downstairs neighbour' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Recommend' }));

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    const [url, opts] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/v1/collections/COL001/invite/propose/');
    expect(JSON.parse(opts.body)).toEqual({
      email: 'lili@example.com',
      note: 'my downstairs neighbour',
    });
  });

  test('the confirmation does not claim an invitation was sent', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    renderRecommend();
    fireEvent.change(screen.getByLabelText(/Their email/i), {
      target: { value: 'lili@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Recommend' }));

    // "Sent to Lala. If they agree, we'll invite them." — conditional, and the
    // recipient named is the owner, not the person recommended.
    const confirmation = await screen.findByText(/Sent to Lala/);
    expect(confirmation).toBeInTheDocument();
    expect(confirmation.textContent).toMatch(/if they agree/i);
  });

  test('"Close" hands back to the page, and the form is the element the button controls', () => {
    const onClose = vi.fn();
    const { container } = renderRecommend(onClose);

    expect(container.querySelector('#recommend-box')).toContainElement(
      screen.getByLabelText(/Their email/i)
    );
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test('a refusal from the server is shown rather than swallowed', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 400, json: () => Promise.resolve({}) });
    renderRecommend();
    fireEvent.change(screen.getByLabelText(/Their email/i), {
      target: { value: 'lili@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Recommend' }));

    expect(await screen.findByText(/couldn't send that/i)).toBeInTheDocument();
  });
});

// A group run by a team: any curator can decide and all of them read the note,
// so four sentences that named the founder would be untrue (the same case as
// the request emails' "the curators"). The server still tells only the
// founder, so none of the four says the curators were told or that anything
// was sent to them — only what is true today.
describe('RecommendGuest — a group run by a team', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });
  afterEach(() => vi.restoreAllMocks());

  test('all four sentences name the curators, and none names the founder', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    const { container } = renderRecommend(vi.fn(), { coOwnerCount: 2 });

    expect(
      screen.getByText(
        'The curators decide — nothing is sent to them until one of the curators says yes.'
      )
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText('Anything the curators should know? (optional)')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Only the curators see this. It helps them decide.')
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Their email/i), {
      target: { value: 'lili@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Recommend' }));
    expect(
      await screen.findByText("Done. If one of the curators agrees, we'll invite them.")
    ).toBeInTheDocument();

    // Not one of the four reads "Lala", and no interpolation was left open.
    expect(container.textContent).not.toMatch(/Lala|\{\{/);
  });

  test('the confirmation is still conditional and claims nothing was sent or invited', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    renderRecommend(vi.fn(), { coOwnerCount: 1 });
    fireEvent.change(screen.getByLabelText(/Their email/i), {
      target: { value: 'lili@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Recommend' }));

    const confirmation = await screen.findByText(/If one of the curators agrees/);
    expect(confirmation.textContent).toMatch(/we'll invite them/i);
    expect(confirmation.textContent).not.toMatch(/\b(invited|sent to|we've sent)\b/i);
  });

  test("with no co-curators the sentences are the founder's own, by name", () => {
    renderRecommend(vi.fn(), { coOwnerCount: 0 });

    expect(screen.getByText(/Lala decides/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Anything Lala should know/i)).toBeInTheDocument();
    expect(screen.getByText(/Only Lala sees this/)).toBeInTheDocument();
    expect(screen.queryByText(/The curators decide/)).toBeNull();
  });
});

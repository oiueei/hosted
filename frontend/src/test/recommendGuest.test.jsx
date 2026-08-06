import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
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
function renderRecommend() {
  return render(
    <MemoryRouter>
      <RecommendGuest collectionCode="COL001" ownerName="Lala" />
    </MemoryRouter>,
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
    fireEvent.click(screen.getByRole('button', { name: /Recommend them/i }));

    expect(screen.getByText(/Lala decides/)).toBeInTheDocument();
    expect(screen.getByText(/nothing is sent to them until they say yes/i)).toBeInTheDocument();
  });

  test('recommending posts the email and the note to the propose endpoint', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    renderRecommend();
    fireEvent.click(screen.getByRole('button', { name: /Recommend them/i }));

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
    fireEvent.click(screen.getByRole('button', { name: /Recommend them/i }));
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

  test('a refusal from the server is shown rather than swallowed', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 400, json: () => Promise.resolve({}) });
    renderRecommend();
    fireEvent.click(screen.getByRole('button', { name: /Recommend them/i }));
    fireEvent.change(screen.getByLabelText(/Their email/i), {
      target: { value: 'lili@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Recommend' }));

    expect(await screen.findByText(/couldn't send that/i)).toBeInTheDocument();
  });
});

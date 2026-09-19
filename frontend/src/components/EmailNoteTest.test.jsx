import { render, screen, fireEvent } from '@testing-library/react';
import { vi, describe, test, expect, beforeEach } from 'vitest';

vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal()),
  apiFetch: vi.fn(),
}));

import { apiFetch } from '../services/api';
import EmailNoteTest from './EmailNoteTest';

const renderTest = (note) =>
  render(<EmailNoteTest collectionCode="COL001" note={note} buttonStyle={{}} />);

const posts = () => apiFetch.mock.calls.filter(([, o]) => o?.method === 'POST');

beforeEach(() => vi.clearAllMocks());

/**
 * A collection's email note appears only in the emails a requester gets, and a
 * curator can't request their own things — so it was written blind. The button
 * mails the curator the draft as typed, through the email's own renderer.
 */
describe('EmailNoteTest', () => {
  test('sends the draft as typed — unsaved — and says where it went', async () => {
    apiFetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: 'sent' }) });
    renderTest('  **Bring ID.**  ');

    fireEvent.click(screen.getByRole('button', { name: 'Send me a test email' }));

    expect(await screen.findByText(/Sent to your inbox/)).toBeInTheDocument();
    expect(posts()).toHaveLength(1);
    const [url, options] = posts()[0];
    expect(url).toBe('/api/v1/collections/COL001/email-note/test/');
    expect(JSON.parse(options.body)).toEqual({ email_note: '**Bring ID.**' });
  });

  test('an empty or over-long note has nothing to send', () => {
    const { rerender } = renderTest('   ');
    expect(screen.getByRole('button', { name: 'Send me a test email' })).toBeDisabled();

    rerender(<EmailNoteTest collectionCode="COL001" note={'x'.repeat(513)} buttonStyle={{}} />);
    expect(screen.getByRole('button', { name: 'Send me a test email' })).toBeDisabled();
  });

  test('a refusal says why, and the rate limit says to wait', async () => {
    apiFetch.mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: async () => ({ error: 'Only the owner or a co-owner can test the email note' }),
    });
    renderTest('Hi.');
    fireEvent.click(screen.getByRole('button', { name: 'Send me a test email' }));
    expect(
      await screen.findByText('Only the owner or a co-owner can test the email note')
    ).toBeInTheDocument();

    apiFetch.mockResolvedValueOnce({ ok: false, status: 429, json: async () => ({}) });
    fireEvent.click(screen.getByRole('button', { name: 'Send me a test email' }));
    expect(await screen.findByText(/Too many attempts/)).toBeInTheDocument();
  });
});

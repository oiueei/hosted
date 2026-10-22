import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';
import ContactPage from '../pages/ContactPage';

// The support channel: public (a locked-out user is the main case), posts to
// /api/v1/contact/ and confirms receipt.

function mockResponse(body, ok = true, status = 200) {
  return { ok, status, json: () => Promise.resolve(body) };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/contact']}>
      <Routes>
        <Route path="/contact" element={<ContactPage />} />
        <Route path="*" element={<div data-testid="navigated" />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('ContactPage', () => {
  beforeEach(() => localStorage.clear());

  test('sends the message and confirms receipt', async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve(mockResponse({ message: 'ok' })));
    renderPage();
    fireEvent.change(screen.getByLabelText(/Email/), {
      target: { value: 'lala@your-domain.test' },
    });
    fireEvent.change(screen.getByLabelText(/Message/), { target: { value: 'Help!' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(
      await screen.findByText("We've got your message — we'll reply as soon as we can.")
    ).toBeInTheDocument();
    const post = globalThis.fetch.mock.calls.find(([, o]) => o?.method === 'POST');
    expect(post[0]).toBe('/api/v1/contact/');
    // No `kind`: the server's default, support, is the only kind a page asks for.
    expect(JSON.parse(post[1].body)).toEqual({
      name: '',
      email: 'lala@your-domain.test',
      message: 'Help!',
    });
  });

  test('the send button sits in a wide row, so on a phone it is the width of the screen', () => {
    renderPage();

    expect(screen.getByRole('button', { name: 'Send' }).parentElement).toHaveClass(
      'button-row-wide'
    );
  });

  test('links nowhere to /collaborate: the page left the front end', () => {
    const { container } = renderPage();

    expect(container.querySelector('a[href="/collaborate"]')).toBeNull();
    expect(screen.queryByText(/Collaborations/)).toBeNull();
  });

  test('a rate limit shows the too-many-attempts message and keeps the form', async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve(mockResponse({}, false, 429)));
    renderPage();
    fireEvent.change(screen.getByLabelText(/Email/), {
      target: { value: 'lala@your-domain.test' },
    });
    fireEvent.change(screen.getByLabelText(/Message/), { target: { value: 'Help!' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(
      await screen.findByText('Too many attempts — please wait a moment and try again.')
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
  });

  async function sendHelp() {
    renderPage();
    fireEvent.change(screen.getByLabelText(/Email/), {
      target: { value: 'lala@your-domain.test' },
    });
    fireEvent.change(screen.getByLabelText(/Message/), { target: { value: 'Help!' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  }

  test('a send that never connects says the connection failed, not that the message was refused', async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new TypeError('Failed to fetch')));
    await sendHelp();
    expect(await screen.findByText('Connection error.')).toBeInTheDocument();
    expect(screen.queryByText("We couldn't send your message. Please try again.")).toBeNull();
  });

  test('a server error says the message could not be sent, and keeps the form', async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve(mockResponse({}, false, 500)));
    await sendHelp();
    expect(
      await screen.findByText("We couldn't send your message. Please try again.")
    ).toBeInTheDocument();
    expect(screen.queryByText('Connection error.')).toBeNull();
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
  });
});

import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';

// Mock the api service so we can drive what /auth/me/ returns during the
// cookie-probe path (userCode absent from localStorage).
vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '../services/api';
import RequireAuth from '../components/RequireAuth';

// Prints where the redirect landed, query and all: the login page's `next` is the
// whole point of the redirect and a bare "Login Page" cannot show it.
function LoginProbe() {
  const { pathname, search } = useLocation();
  return <div>{`Login Page ${pathname}${search}`}</div>;
}

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<LoginProbe />} />
        <Route element={<RequireAuth />}>
          <Route path="/secret" element={<div>Secret Page</div>} />
          <Route path="/collections/new" element={<div>New Collection</div>} />
          <Route path="/" element={<div>Home</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe('RequireAuth', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  test('renders the protected route immediately when a userCode is present', () => {
    localStorage.setItem('userCode', 'ABC123');
    renderAt('/secret');
    expect(screen.getByText('Secret Page')).toBeInTheDocument();
    // Fast path — no cookie probe.
    expect(apiFetch).not.toHaveBeenCalled();
  });

  test('redirects to /login when no userCode and /auth/me/ is unauthorised', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 401, json: () => Promise.resolve(null) });
    renderAt('/secret');
    expect(await screen.findByText(/^Login Page \/login/)).toBeInTheDocument();
    expect(screen.queryByText('Secret Page')).toBeNull();
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/auth/me/', expect.anything());
  });

  test('an anonymous reader is sent to /login remembering the page they wanted', async () => {
    // The magic link they ask for then brings them back here, not to Home.
    apiFetch.mockResolvedValue({ ok: false, status: 401, json: () => Promise.resolve(null) });
    renderAt('/collections/new');

    expect(
      await screen.findByText('Login Page /login?next=%2Fcollections%2Fnew')
    ).toBeInTheDocument();
  });

  test('from Home there is nothing to come back to, so a plain /login', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 401, json: () => Promise.resolve(null) });
    renderAt('/');

    expect(await screen.findByText('Login Page /login')).toBeInTheDocument();
  });

  test('recovers the session when cookies are valid but userCode was missing', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ code: 'ABC123' }),
    });
    renderAt('/secret');
    expect(await screen.findByText('Secret Page')).toBeInTheDocument();
    // userCode is re-seeded so downstream ownership checks work.
    expect(localStorage.getItem('userCode')).toBe('ABC123');
  });
});

import { readFileSync } from 'node:fs';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';

/**
 * "Ideas and bugs" at the foot of Home (CA, 2026-10-03): a secondary button, alone,
 * in its own container — and only where the deployment sets `VITE_FEEDBACK_URL`,
 * read once when `FeedbackLink` loads, so each test stubs it and imports Home anew.
 */
const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'USR001');
  vi.clearAllMocks();
  apiFetch.mockImplementation((url) => {
    if (url.startsWith('/api/v1/auth/me/')) {
      return ok({ code: 'USR001', name: 'Lulu', email: 'lulu@example.com', koro: 'basic' });
    }
    if (url.startsWith('/api/v1/collections/')) return ok({ results: [] });
    return ok([]);
  });
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

async function renderHome(feedbackUrl) {
  vi.stubEnv('VITE_FEEDBACK_URL', feedbackUrl);
  const { default: HomePage } = await import('../pages/HomePage');
  return render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>
  );
}

describe('Home and the feedback button', () => {
  test('with a feedback URL, "Ideas and bugs" is at the foot, in its own container', async () => {
    const { container } = await renderHome('https://forms.example/feedback');

    const link = await screen.findByRole('link', { name: /^Ideas and bugs/ });
    expect(link).toHaveAttribute('href', 'https://forms.example/feedback');
    expect(link.parentElement).toHaveClass('feedback-link');
    expect(container.querySelectorAll('.feedback-link')).toHaveLength(1);
  });

  test("it is the secondary button: white background, not the theeeme's primary fill", async () => {
    await renderHome('https://forms.example/feedback');

    const link = await screen.findByRole('link', { name: /^Ideas and bugs/ });
    expect(link.style.getPropertyValue('--background-color')).toBe('var(--color-white)');
  });

  test('without one there is no button, and the container is empty (the CSS hides it)', async () => {
    const { container } = await renderHome('');

    await screen.findByText(/Lulu/);
    expect(screen.queryByRole('link', { name: /Ideas and bugs/ })).toBeNull();
    expect(container.querySelector('.feedback-link')).toBeEmptyDOMElement();
  });

  test('the stylesheet hides an empty container, so upstream gets no gap at the foot', () => {
    // jsdom applies no CSS; the contract is the rule. The wrapper's margin-top
    // would otherwise survive an empty `<div>` (an empty block's margins still count).
    const css = readFileSync('src/App.css', 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');

    expect(css).toMatch(/\.feedback-link:empty\s*\{\s*display:\s*none;?\s*\}/);
  });
});

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect } from 'vitest';

import '../testI18n';

// Mock the shared join page down to just its children, so this test pins the
// WIRING (PopInPage hands MagicLinkJoinPage a /faq link) independently of the
// shared component's own rendering — the `children` slot itself is tested in
// `src/components/MagicLinkJoinPage.test.jsx`.
vi.mock('../../components/MagicLinkJoinPage', () => ({
  default: ({ ns, endpoint, children }) => (
    <div data-ns={ns} data-endpoint={endpoint}>
      {children}
    </div>
  ),
}));

import PopInPage from './PopInPage';
import { faqPath } from '../index';

describe('PopInPage', () => {
  test('points its footer link at this deployment’s /faq', () => {
    render(
      <MemoryRouter>
        <PopInPage />
      </MemoryRouter>
    );

    const link = screen.getByRole('link', { name: /frequently asked questions/i });
    expect(link).toHaveAttribute('href', faqPath);
  });

  test('still posts to the hosted pop-in endpoint, not /auth/join/', () => {
    render(
      <MemoryRouter>
        <PopInPage />
      </MemoryRouter>
    );

    expect(document.querySelector('[data-endpoint="/api/v1/auth/pop-in/"]')).not.toBeNull();
  });
});

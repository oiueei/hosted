import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect } from 'vitest';

import '../testI18n';

// Mock the shared join page down to just its children, so this test pins the
// WIRING (PopInPage hands MagicLinkJoinPage a /faq link) independently of the
// shared component's own rendering — the `children` slot itself is tested in
// `src/components/MagicLinkJoinPage.test.jsx`.
vi.mock('../../components/MagicLinkJoinPage', () => ({
  default: ({ ns, endpoint, offerSignIn, children }) => (
    <div data-ns={ns} data-endpoint={endpoint} data-offer-sign-in={String(offerSignIn)}>
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

  test('asks the shared join page not to offer "Already have an account?"', () => {
    // CA, 2026-10-03: /welcome offers it; /popin does not repeat it. The shared
    // component is core's, so what turns the button off is this prop — and the
    // default (absent) would leave it on, which is why it is `false`, not unset.
    render(
      <MemoryRouter>
        <PopInPage />
      </MemoryRouter>
    );

    expect(document.querySelector('[data-ns="popin"]')).toHaveAttribute(
      'data-offer-sign-in',
      'false'
    );
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

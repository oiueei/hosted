import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect, afterEach } from 'vitest';
import i18n from 'i18next';

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
  test('offers the FAQ as a full-width secondary button at this deployment’s /faq', () => {
    render(
      <MemoryRouter>
        <PopInPage />
      </MemoryRouter>
    );

    const link = screen.getByRole('link', { name: 'Frequently asked questions' });
    expect(link).toHaveAttribute('href', faqPath);
    // One <a> in the shape of a button, as wide as the form above it — not a line of text.
    expect(link.tagName).toBe('A');
    expect(link.className).toMatch(/hds-button/);
    expect(link).toHaveClass('button-link--full');
    expect(link.closest('p')).toBeNull();
    // The secondary tokens: a white fill, where the primary button wears the theeeme's colour.
    expect(link.style.getPropertyValue('--background-color')).toBe('var(--color-white)');
  });

  test('asks the shared join page not to offer "Already have an account?"', () => {
    // /welcome offers it; /popin does not repeat it. The shared
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

describe('PopInPage — the FAQ button reads as the question alone, in every language', () => {
  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  test.each([
    ['en', 'Frequently asked questions'],
    ['es', 'Preguntas frecuentes'],
    ['ca', 'Preguntes freqüents'],
  ])('in %s it reads "%s", with no arrow', async (language, label) => {
    await i18n.changeLanguage(language);
    render(
      <MemoryRouter>
        <PopInPage />
      </MemoryRouter>
    );

    const link = screen.getByRole('link', { name: label });
    expect(link).toHaveAttribute('href', faqPath);
    expect(link.textContent).toBe(label);
  });
});

import { render, screen, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';
import i18n from 'i18next';

import './testI18n';
import { externalForms } from './index';
import SiteFooter from '../components/SiteFooter';
import FeedbackLink from '../components/FeedbackLink';
import ApprovalNotice from '../components/ApprovalNotice';

/**
 * The three ways of writing to the team are forms on Tally on this deployment (TL1 in
 * core, TLH1 here; CA, 2026-10-05): the footer's "Contact us", "Ideas and bugs" and
 * "Request access", in the language of whoever opens them and in a new tab, each address
 * exactly as CA gave it — no parameter, no return page. Core's own tests pin how the
 * three places use `externalForms` with the module mocked; this file pins what THIS
 * deployment puts in it, and that the real module reaches the real places.
 */
const NINE = {
  contact: {
    es: 'https://tally.so/r/PdaOy1',
    ca: 'https://tally.so/r/Gx2lye',
    en: 'https://tally.so/r/Y5LagN',
  },
  feedback: {
    es: 'https://tally.so/r/lbZRb5',
    ca: 'https://tally.so/r/68XN1O',
    en: 'https://tally.so/r/A76Xkz',
  },
  requestAccess: {
    es: 'https://tally.so/r/zxaY4M',
    ca: 'https://tally.so/r/D4lz9N',
    en: 'https://tally.so/r/aQ8dPX',
  },
};

describe('what this deployment puts in externalForms', () => {
  test('the nine addresses CA gave, exactly: three forms, three languages each', () => {
    expect(externalForms).toEqual(NINE);
  });

  test('all nine are Tally forms, written as a bare address with nothing added', () => {
    const urls = Object.values(externalForms).flatMap((byLanguage) => Object.values(byLanguage));

    expect(urls).toHaveLength(9);
    for (const url of urls) {
      expect(url).toMatch(/^https:\/\/tally\.so\/r\/[A-Za-z0-9]+$/);
    }
  });

  test('no two of them are the same form: a language is not pointing at another’s', () => {
    const urls = Object.values(externalForms).flatMap((byLanguage) => Object.values(byLanguage));

    expect(new Set(urls).size).toBe(9);
  });
});

describe('the real module reaches the three places, in each language', () => {
  window.scrollTo = vi.fn();

  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });
  afterEach(async () => {
    await act(async () => {
      await i18n.changeLanguage('en');
    });
  });

  const withCapabilities = () => {
    localStorage.setItem('userCode', `U${Math.random()}`);
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            capabilities: {
              collection_modes: ['PROPRIETARY'],
              thing_types: [],
              // What the server says when there is a form: not the one used.
              request_url: 'https://server.example/request-access/',
            },
          }),
      })
    );
  };

  test.each(['es', 'ca', 'en'])(
    'in %s: "Contact us", "Ideas and bugs" and "Request access"',
    async (language) => {
      withCapabilities();
      await act(async () => {
        await i18n.changeLanguage(language);
      });
      const { container } = render(
        <MemoryRouter>
          <FeedbackLink />
          <ApprovalNotice
            kind="collection_modes"
            catalogue={[
              { value: 'PROPRIETARY', label: 'Just mine' },
              { value: 'COMMUNITY', label: 'Shared' },
            ]}
          />
          <SiteFooter />
        </MemoryRouter>
      );

      const hrefs = () => [...container.querySelectorAll('a[target="_blank"]')].map((a) => a.href);
      await waitFor(() => expect(hrefs()).toHaveLength(3));
      expect(hrefs().sort()).toEqual(
        [NINE.contact[language], NINE.feedback[language], NINE.requestAccess[language]].sort()
      );
      // The footer no longer leads to the app's own page, and the server's address is unused.
      expect(container.querySelector('footer a[href="/contact"]')).toBeNull();
      expect(screen.queryByRole('link', { name: /server\.example/ })).toBeNull();
      expect(
        container.querySelector('a[href="https://server.example/request-access/"]')
      ).toBeNull();
    }
  );
});

import { StrictMode } from 'react';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';
import i18n from 'i18next';
import { axe, toHaveNoViolations } from 'jest-axe';

import './testI18n';
import AccessPage from './pages/AccessPage';
import { deploymentI18n } from './i18n';
import { settle, switchLanguage } from '../test/settle';

expect.extend(toHaveNoViolations);

/**
 * `/access/:need` — what opens on request, one section per need.
 *
 * What it protects: the page says the two things that need asking for, always in
 * that order; a person sent here for one of them lands on it; the section reports
 * itself once, as a number and nothing more, and a failing report is never shown;
 * and each section has its own "Request access" button, so the press can be told
 * apart by need.
 */

window.scrollTo = vi.fn();
const NEEDS = ['library', 'shed'];
const SEEN = '/api/v1/access/seen/';

const seenCalls = () => fetch.mock.calls.filter(([url]) => url === SEEN);

function renderAt(path, { strict = false } = {}) {
  const tree = (
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/access/:need" element={<AccessPage />} />
        <Route path="/access" element={<AccessPage />} />
      </Routes>
    </MemoryRouter>
  );
  return render(strict ? <StrictMode>{tree}</StrictMode> : tree);
}

beforeEach(async () => {
  localStorage.clear();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) })
  );
  Element.prototype.scrollIntoView = vi.fn();
  await switchLanguage(i18n, 'en');
});

describe('the sections', () => {
  test('both, always, in the same order, each under its own heading', async () => {
    renderAt('/access/library');
    await settle(fetch);

    const headings = screen.getAllByRole('heading', { level: 2 });
    expect(headings.map((h) => h.id)).toEqual(NEEDS);
    expect(headings.map((h) => h.textContent)).toEqual(['Library of Things', 'Shed']);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('What opens on request');
  });

  test('each section has its own button to the form, for its own need, in a new tab', async () => {
    renderAt('/access');
    await settle(fetch);

    for (const need of NEEDS) {
      const section = document.getElementById(need).closest('section');
      const button = within(section).getByRole('link', { name: /Request access/ });
      expect(button).toHaveAttribute('href', `/request-access/?for=${need}`);
      expect(button).toHaveAttribute('target', '_blank');
      expect(button).toHaveAttribute('rel', 'noopener noreferrer');
      expect(button).toHaveAccessibleName('Request access. Opens in a new tab.');
      expect(button.className).toMatch(/hds-button/);
      expect(within(section).getByText(/opens in a new tab\. We'll answer you by email/i));
    }
  });

  test('the tab is called after the page', async () => {
    renderAt('/access');
    await settle(fetch);

    expect(document.title).toBe('Request access — OIUEEI');
  });
});

describe('arriving for one need', () => {
  test('/access/library: the page goes to that section, focuses its heading and reports it once', async () => {
    renderAt('/access/library');
    await settle(fetch);

    const heading = document.getElementById('library');
    expect(document.activeElement).toBe(heading);
    expect(heading).toHaveAttribute('tabindex', '-1');
    expect(heading.scrollIntoView).toBeDefined();
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);
    expect(seenCalls()).toHaveLength(1);
    const [, options] = seenCalls()[0];
    expect(options.method).toBe('POST');
    expect(JSON.parse(options.body)).toEqual({ need: 'library' });
  });

  test.each([['/access'], ['/access/nothing'], ['/access/rent'], ['/access/community']])(
    '%s: the whole page, nowhere to go and nothing reported',
    async (path) => {
      renderAt(path);
      await settle(fetch);

      expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(2);
      expect(seenCalls()).toHaveLength(0);
      expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
      expect(NEEDS.map((n) => document.getElementById(n) === document.activeElement)).toEqual([
        false,
        false,
      ]);
    }
  );

  test('drawing it again, StrictMode included, never reports twice', async () => {
    const { rerender } = renderAt('/access/shed', { strict: true });
    await settle(fetch);
    rerender(
      <StrictMode>
        <MemoryRouter initialEntries={['/access/shed']}>
          <Routes>
            <Route path="/access/:need" element={<AccessPage />} />
          </Routes>
        </MemoryRouter>
      </StrictMode>
    );
    await settle(fetch);

    expect(seenCalls()).toHaveLength(1);
  });

  test('a report that fails is not shown to anyone', async () => {
    fetch.mockImplementation((url) =>
      url === SEEN ? Promise.reject(new Error('offline')) : Promise.resolve({ ok: true })
    );
    renderAt('/access/library');
    await settle(fetch);

    expect(seenCalls()).toHaveLength(1);
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(2);
  });

  test('a report the server refuses is not shown either', async () => {
    fetch.mockResolvedValue({ ok: false, status: 429, json: () => Promise.resolve({}) });
    renderAt('/access/shed');
    await settle(fetch);

    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('in every language', () => {
  test.each([
    ['es', 'Lo que se abre con una solicitud', 'Biblioteca de las cosas', 'Pedir acceso'],
    ['ca', "El que s'obre amb una sol·licitud", 'Biblioteca de les coses', 'Demanar accés'],
  ])('%s speaks its own words', async (lang, title, library, button) => {
    await switchLanguage(i18n, lang);
    renderAt('/access');
    await settle(fetch);

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(title);
    expect(document.getElementById('library')).toHaveTextContent(library);
    expect(screen.getAllByRole('link', { name: new RegExp(button) })).toHaveLength(2);
  });

  test('the texts are the ones written for the page, word for word', () => {
    expect(deploymentI18n.en.access.title).toBe('What opens on request');
    expect(deploymentI18n.es.access.library.body).toBe(
      'Presta tus cosas, gratis o con precio: se las llevan a casa y las devuelven. Tú eliges qué días se recogen y se devuelven, confirmas o rechazas cada solicitud y puedes explicar cómo funcionan las fianzas.'
    );
    expect(deploymentI18n.en.access.intro).toBe(
      'Here anyone can open a stall to give things away or sell them. Lending, renting out or booking creates a commitment to other people: a thing that has to come back, a space that gets booked. So before opening it we ask you for two sentences on who you are and what you want to share. A person reads them.'
    );
    expect(deploymentI18n.ca.access.intro).toBe(
      "Aquí qualsevol pot obrir una paradeta per regalar o vendre. Deixar, llogar o reservar crea un compromís amb altres persones: una cosa que ha de tornar, un espai que es reserva. Per això, abans d'obrir-ho, et demanem dues frases sobre qui ets i què vols compartir. Les llegeix una persona."
    );
    // The two sections the page dropped have no copy left.
    for (const lang of ['en', 'es', 'ca']) {
      expect(Object.keys(deploymentI18n[lang].access)).not.toContain('rent');
      expect(Object.keys(deploymentI18n[lang].access)).not.toContain('community');
    }
    expect(deploymentI18n.ca.access.formNote).toBe(
      "El formulari s'obre en una altra pestanya. Et responem per correu."
    );
  });
});

describe('accessibility', () => {
  test('no violations, heading order included', async () => {
    const { container } = renderAt('/access/library');
    await settle(fetch);

    expect(await axe(container)).toHaveNoViolations();
  });
});

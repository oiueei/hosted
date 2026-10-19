import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import NewVersionNotice from '../components/NewVersionNotice';
import { press } from '../test/settle';
import { CHECK_EVERY_MS } from './useNewVersion';

const MINE = '/static/assets/index-AAAA1111.js';

const page = (src) =>
  `<!doctype html><html><head><link rel="modulepreload" href="/static/assets/vendor-react-ZZ.js">` +
  `</head><body><div id="root"></div>` +
  (src ? `<script type="module" crossorigin src="${src}"></script>` : '') +
  `</body></html>`;

const served = (html) =>
  Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(html) });

let visibility;
const comeBack = async () => {
  await act(async () => {
    document.dispatchEvent(new Event('visibilitychange'));
    // The reply and its parsing are promises: let them all land inside `act`.
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
};

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-19T09:00:00Z'));
  vi.stubEnv('PROD', true);
  visibility = 'visible';
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility });
  // The page the tab is running names its entry script, like the built index.html does.
  const script = document.createElement('script');
  script.type = 'module';
  script.src = MINE;
  document.head.appendChild(script);
  globalThis.fetch = vi.fn();
});

afterEach(() => {
  document.querySelectorAll('script[type="module"]').forEach((el) => el.remove());
  delete document.visibilityState;
  vi.unstubAllEnvs();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('the new-version notice', () => {
  test('the same entry script says nothing', async () => {
    fetch.mockReturnValue(served(page(MINE)));
    render(<NewVersionNotice />);

    await comeBack();

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("There's a new version of OIUEEI.")).toBeNull();
  });

  test('a different entry script shows the notice, with a Reload button and a close', async () => {
    fetch.mockReturnValue(served(page('/static/assets/index-BBBB2222.js')));
    render(<NewVersionNotice />);

    await comeBack();

    expect(await screen.findByText("There's a new version of OIUEEI.")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();
  });

  test('it asks for the front page of this origin, with nothing added to the request', async () => {
    fetch.mockReturnValue(served(page(MINE)));
    render(<NewVersionNotice />);

    await comeBack();

    expect(fetch.mock.calls[0]).toEqual(['/']);
  });

  test('Reload reloads the page; nothing reloads by itself', async () => {
    const reload = vi.fn();
    const original = window.location;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...original, reload },
    });
    try {
      fetch.mockReturnValue(served(page('/static/assets/index-BBBB2222.js')));
      render(<NewVersionNotice />);
      await comeBack();
      expect(reload).not.toHaveBeenCalled();

      await press(await screen.findByRole('button', { name: 'Reload' }));

      expect(reload).toHaveBeenCalledTimes(1);
    } finally {
      Object.defineProperty(window, 'location', { configurable: true, value: original });
    }
  });

  test('closing it hides it and does not ask again', async () => {
    fetch.mockReturnValue(served(page('/static/assets/index-BBBB2222.js')));
    render(<NewVersionNotice />);
    await comeBack();

    await press(await screen.findByRole('button', { name: 'Close' }));
    await waitFor(() => expect(screen.queryByText("There's a new version of OIUEEI.")).toBeNull());
    await act(async () => {
      vi.setSystemTime(Date.now() + 2 * CHECK_EVERY_MS);
    });
    await comeBack();

    expect(screen.queryByText("There's a new version of OIUEEI.")).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  test('two returns inside ten minutes make one request, a later one makes another', async () => {
    fetch.mockReturnValue(served(page(MINE)));
    render(<NewVersionNotice />);

    await comeBack();
    await act(async () => {
      vi.setSystemTime(Date.now() + CHECK_EVERY_MS - 1000);
    });
    await comeBack();
    expect(fetch).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.setSystemTime(Date.now() + 2000);
    });
    await comeBack();
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  test('a tab that goes out of view asks nothing', async () => {
    fetch.mockReturnValue(served(page(MINE)));
    render(<NewVersionNotice />);

    visibility = 'hidden';
    await comeBack();

    expect(fetch).not.toHaveBeenCalled();
  });

  test('a failed request shows nothing, and the next window tries again', async () => {
    fetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    render(<NewVersionNotice />);

    await comeBack();
    expect(screen.queryByText("There's a new version of OIUEEI.")).toBeNull();

    fetch.mockReturnValue(served(page('/static/assets/index-BBBB2222.js')));
    await act(async () => {
      vi.setSystemTime(Date.now() + CHECK_EVERY_MS + 1);
    });
    await comeBack();
    expect(await screen.findByText("There's a new version of OIUEEI.")).toBeInTheDocument();
  });

  test('an error status, or a page with no entry script, shows nothing', async () => {
    fetch.mockReturnValueOnce(Promise.resolve({ ok: false, status: 503, text: async () => '' }));
    render(<NewVersionNotice />);
    await comeBack();

    fetch.mockReturnValue(served(page(null)));
    await act(async () => {
      vi.setSystemTime(Date.now() + CHECK_EVERY_MS + 1);
    });
    await comeBack();

    expect(fetch).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("There's a new version of OIUEEI.")).toBeNull();
  });

  test('in development it never asks', async () => {
    vi.stubEnv('PROD', false);
    fetch.mockReturnValue(served(page('/static/assets/index-BBBB2222.js')));
    render(<NewVersionNotice />);

    await comeBack();

    expect(fetch).not.toHaveBeenCalled();
    expect(screen.queryByText("There's a new version of OIUEEI.")).toBeNull();
  });

  test('the words exist in the three languages', async () => {
    const [en, es, ca] = await Promise.all(
      ['en', 'es', 'ca'].map((l) => import(`../i18n/locales/${l}.json`).then((m) => m.default))
    );
    expect(es.newVersion).toEqual({ body: 'Hay una versión nueva de OIUEEI.', reload: 'Recargar' });
    expect(ca.newVersion).toEqual({
      body: "Hi ha una versió nova d'OIUEEI.",
      reload: 'Torna a carregar',
    });
    expect(en.newVersion.reload).toBe('Reload');
  });
});

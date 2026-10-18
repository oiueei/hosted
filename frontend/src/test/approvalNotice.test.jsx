import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';
import { axe, toHaveNoViolations } from 'jest-axe';

expect.extend(toHaveNoViolations);

import ApprovalNotice from '../components/ApprovalNotice';
import { isOfferable } from '../hooks/useCapabilities';

// This file is about what a deployment with no forms of its own hosted elsewhere shows
// — the app's own contact page, `VITE_FEEDBACK_URL`, the server's request address. A
// core test cannot assume what `deployment/` holds, so the
// `externalForms` a deployment may have are switched off here by stubbing the helper
// that reads them; `externalForms.test.jsx` pins them on, with the module mocked.
vi.mock('../utils/externalForms', () => ({ externalFormUrl: () => null }));
// The pages a deployment may send "Request access" to (`requestAccessPaths`) are switched
// off the same way: this file pins what the standalone shows, whatever `deployment/` holds.
vi.mock('../deployment', async (orig) => ({ ...(await orig()), requestAccessPaths: {} }));

/**
 * The notice a narrowed deployment owes anyone looking at a shorter list than
 * the product has, and the predicate that shortens it.
 *
 * **Upstream it never appears.** OIUEEI withholds nothing, so every assertion
 * about it rendering is about somebody else's deployment — which is the point
 * of it living here: the React is identical in both, and a deployment narrows
 * the policy on the server without editing a form component.
 *
 * The failure it prevents is a form that quietly offers less than the product
 * does, leaving the user to conclude the feature does not exist — which, when
 * there is a page to request it on, is not even true.
 */

const MODES = [
  { value: 'PROPRIETARY', label: 'Just mine' },
  { value: 'COMMUNITY', label: 'Shared' },
];

function mockCapabilities(capabilities) {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ capabilities }) })
  );
}

beforeEach(() => {
  vi.resetModules();
  localStorage.clear();
  // The hook caches one request per signed-in account; a fresh code per test
  // keeps them independent without exporting a reset nobody would call in prod.
  localStorage.setItem('userCode', `U${Math.random()}`);
});

describe('the standalone renders nothing', () => {
  test('silent when every option is allowed', async () => {
    mockCapabilities({
      collection_modes: ['PROPRIETARY', 'COMMUNITY'],
      thing_types: [],
      request_url: null,
    });

    const { container } = render(<ApprovalNotice kind="collection_modes" catalogue={MODES} />);

    // Waiting for the fetch to settle first: asserting on an empty render
    // before it resolves would pass no matter what the answer turned out to be.
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  test('silent while the answer is unknown, and if it never arrives', async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('offline')));

    const { container } = render(<ApprovalNotice kind="collection_modes" catalogue={MODES} />);

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    // A wrong "this needs approval" on a deployment that approves everything is
    // worse than silence — the form still works, so say nothing.
    expect(container).toBeEmptyDOMElement();
  });
});

describe('a deployment that withholds something', () => {
  test('names what is missing, in the words the form used', async () => {
    mockCapabilities({
      collection_modes: ['PROPRIETARY'],
      thing_types: [],
      request_url: 'https://example.test/ask/',
    });

    render(<ApprovalNotice kind="collection_modes" catalogue={MODES} />);

    // "Shared", the label the radio would have carried — not COMMUNITY, which
    // names a database value the reader has never seen.
    expect(await screen.findByText(/Shared/)).toBeInTheDocument();
    expect(screen.queryByText(/COMMUNITY/)).not.toBeInTheDocument();
  });

  // "Request access" is a primary button, not a text link ending
  // in an arrow. It is built as `FeedbackLink` is: the real button CSS on one `<a>`.
  describe('where to ask is a primary button', () => {
    const withRequestUrl = () =>
      mockCapabilities({
        collection_modes: ['PROPRIETARY'],
        thing_types: [],
        request_url: 'https://example.test/ask/',
      });
    const renderNotice = () => render(<ApprovalNotice kind="collection_modes" catalogue={MODES} />);

    test('a link made to look like a button, named "Request access", to where access is requested', async () => {
      withRequestUrl();
      renderNotice();

      const button = await screen.findByRole('link', { name: /^Request access/ });
      expect(button).toHaveAttribute('href', 'https://example.test/ask/');
      expect(button).toHaveAttribute('target', '_blank');
      expect(button).toHaveAttribute('rel', expect.stringContaining('noopener'));
      // The words on the button are only the words: no arrow, and no "(opens in a
      // new tab)" printed — the new tab is announced, not shown.
      expect(button).toHaveTextContent(/^Request access$/);
      expect(button).toHaveAccessibleName('Request access. Opens in a new tab.');
      // The real button CSS on the one `<a>` (HDS's `useButtonStyles`): a link with a
      // button's tokens and no button class would only look like one by accident.
      expect(button.className).toMatch(/hds-button/);
    });

    test('it wears the theeeme’s primary tokens', async () => {
      localStorage.setItem(
        'theeemeColors',
        JSON.stringify({
          color_01: 'bus',
          color_02: 'suomenlinna-light',
          color_03: 'copper',
          color_04: 'black',
          color_05: 'white',
          color_06: 'white',
        })
      );
      withRequestUrl();
      renderNotice();

      const button = await screen.findByRole('link', { name: /^Request access/ });
      // Primary: the theeeme's fill — the secondary's background is white.
      expect(button.style.getPropertyValue('--background-color')).toBe('var(--color-bus)');
      expect(button.style.getPropertyValue('--border-color')).toBe('var(--color-bus)');
    });

    test('it sits in a wide row under the sentence, which keeps its words and loses its arrow', async () => {
      withRequestUrl();
      const { container } = renderNotice();

      const button = await screen.findByRole('link', { name: /^Request access/ });
      expect(button.parentElement).toHaveClass('button-row-wide');
      const sentence = container.querySelector('p.approval-notice');
      expect(sentence).toHaveTextContent(/Shared/);
      expect(sentence.textContent).not.toMatch(/→|Request access/);
      // Under the sentence, not inside it.
      expect(sentence).not.toContainElement(button);
      expect(sentence.compareDocumentPosition(button)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    });

    test('it is the only link in the notice', async () => {
      withRequestUrl();
      renderNotice();

      await screen.findByRole('link', { name: /^Request access/ });
      expect(screen.getAllByRole('link')).toHaveLength(1);
    });
  });

  test('with nowhere to ask, says so instead of inviting a request', async () => {
    mockCapabilities({ collection_modes: ['PROPRIETARY'], thing_types: [], request_url: null });

    render(<ApprovalNotice kind="collection_modes" catalogue={MODES} />);

    // "Not here" and "not yet" are different facts. Pointing someone at a
    // request page that does not exist is worse than the shortened list it
    // was meant to explain.
    expect(await screen.findByText(/not available/i)).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    // No button, and no row waiting for one.
    expect(document.querySelector('.button-row-wide')).toBeNull();
  });
});

describe('isOfferable — the predicate the forms filter with', () => {
  test('offers everything while capabilities are unknown', () => {
    // Fail open: this is a courtesy to the user, never the gate. The gate is
    // the server, which refuses regardless of what the browser fetched.
    expect(isOfferable(null, 'thing_types', 'LEND_THING')).toBe(true);
  });

  test('offers what the policy allows and withholds what it does not', () => {
    const capabilities = { thing_types: ['GIFT_THING'] };

    expect(isOfferable(capabilities, 'thing_types', 'GIFT_THING')).toBe(true);
    expect(isOfferable(capabilities, 'thing_types', 'LEND_THING')).toBe(false);
  });

  test('always offers the value being edited, allowed or not', () => {
    /* Grandfathering, mirroring the server: it only judges a *change*, so a
       thing already offered under a withheld verb has to stay editable — and a
       form that dropped the current value from its own selector would display
       a different answer than the one it is about to submit. */
    const capabilities = { thing_types: ['GIFT_THING'] };

    expect(isOfferable(capabilities, 'thing_types', 'LEND_THING', 'LEND_THING')).toBe(true);
    expect(isOfferable(capabilities, 'thing_types', 'RENT_THING', 'LEND_THING')).toBe(false);
  });
});

// A deployment may send a request for access to a page of its own instead of to a form
// hosted elsewhere: `requestAccessPaths` maps a withheld value to a route of the app.
// The module is mocked, since upstream's map is empty and a replacement can only be
// exercised this way (the mock gives every export of the module).
describe('a deployment that has a page of its own to ask on', () => {
  const KINDS = [
    { value: 'STALL', label: 'Stall' },
    { value: 'LIBRARY', label: 'Library' },
    { value: 'SHED', label: 'Shed' },
  ];

  afterEach(() => {
    vi.doUnmock('../deployment');
    vi.doUnmock('../utils/externalForms');
  });

  const Where = () => <p data-testid="where">{useLocation().pathname}</p>;

  async function setUp({ paths, form = null, requestUrl = null, held = ['LIBRARY', 'SHED'] }) {
    vi.resetModules();
    vi.doMock('../deployment', () => ({
      deploymentRoutes: [],
      popInPath: null,
      aboutPath: null,
      faqPath: null,
      externalForms: null,
      deploymentI18n: {},
      requestAccessPaths: paths,
    }));
    vi.doMock('../utils/externalForms', () => ({ externalFormUrl: () => form }));
    mockCapabilities({
      collection_kinds: KINDS.map((k) => k.value).filter((v) => !held.includes(v)),
      collection_modes: ['PROPRIETARY'],
      thing_types: [],
      request_url: requestUrl,
    });
    const { default: Notice } = await import('../components/ApprovalNotice');
    return render(
      <MemoryRouter initialEntries={['/new']}>
        <Routes>
          <Route
            path="/new"
            element={
              <>
                <Notice kind="collection_kinds" catalogue={KINDS} />
                <Where />
              </>
            }
          />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    );
  }

  test('a withheld value with a page sends the request there, in the same tab', async () => {
    await setUp({ paths: { LIBRARY: '/access/library' }, requestUrl: 'https://example.test/ask/' });

    const button = await screen.findByRole('link', { name: 'Request access' });
    expect(button).toHaveAttribute('href', '/access/library');
    expect(button).not.toHaveAttribute('target');
    expect(button).not.toHaveAttribute('rel');
    expect(button).toHaveAccessibleName('Request access');
    expect(button.className).toMatch(/hds-button/);
    expect(button.parentElement).toHaveClass('button-row-wide');
    expect(screen.getAllByRole('link')).toHaveLength(1);
  });

  test('a plain click navigates inside the app', async () => {
    await setUp({ paths: { LIBRARY: '/access/library' } });

    fireEvent.click(await screen.findByRole('link', { name: 'Request access' }));

    expect(await screen.findByTestId('where')).toHaveTextContent('/access/library');
  });

  test('the first withheld value, in the order of the catalogue, that has a page decides', async () => {
    await setUp({ paths: { SHED: '/access/shed', LIBRARY: '/access/library' } });

    const button = await screen.findByRole('link', { name: 'Request access' });
    expect(button).toHaveAttribute('href', '/access/library');
  });

  test('a withheld value with no page keeps opening the address it always did, in a new tab', async () => {
    await setUp({
      paths: { LIBRARY: '/access/library' },
      held: ['SHED'],
      form: 'https://forms.example/acceso',
    });

    const button = await screen.findByRole('link', { name: /^Request access/ });
    expect(button).toHaveAttribute('href', 'https://forms.example/acceso');
    expect(button).toHaveAttribute('target', '_blank');
    expect(button).toHaveAccessibleName('Request access. Opens in a new tab.');
  });

  test('the sentence above does not change', async () => {
    const { container } = await setUp({ paths: { LIBRARY: '/access/library' } });

    await screen.findByRole('link', { name: 'Request access' });
    expect(container.querySelector('p.approval-notice')).toHaveTextContent(
      'Some options need approval on this deployment: Library, Shed.'
    );
  });

  test('upstream, with no pages, nothing changes: the server’s address in a new tab', async () => {
    await setUp({ paths: {}, requestUrl: 'https://example.test/ask/' });

    const button = await screen.findByRole('link', { name: /^Request access/ });
    expect(button).toHaveAttribute('href', 'https://example.test/ask/');
    expect(button).toHaveAttribute('target', '_blank');
  });

  test('upstream, with no address of any kind, it is still the sentence and no button', async () => {
    await setUp({ paths: {} });

    expect(await screen.findByText(/not available/i)).toBeInTheDocument();
    expect(screen.queryByRole('link')).toBeNull();
  });

  test('no axe violations', async () => {
    const { container } = await setUp({ paths: { LIBRARY: '/access/library' } });

    await screen.findByRole('link', { name: 'Request access' });
    expect(await axe(container)).toHaveNoViolations();
  });
});

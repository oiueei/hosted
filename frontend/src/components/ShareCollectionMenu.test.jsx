import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

// The QR image is a picture a test cannot read, and what this component owns is
// not the drawing — it is *which string* it hands the library. Standing in for
// `qrcode.react` is what turns "a dialog appeared" into "the invite link is the
// thing being encoded"; without it the assertion below passes on an empty code.
vi.mock('qrcode.react', () => ({
  QRCodeSVG: ({ value, title }) => <div data-testid="qr" data-value={value} aria-label={title} />,
}));

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
  ),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import ShareCollectionMenu from './ShareCollectionMenu';

const props = {
  collectionCode: 'COL001',
  collectionHeadline: 'My Collection',
  ownerName: 'Owner',
};

function openMenu() {
  // HDS Select renders a button that toggles the options listbox.
  const trigger =
    screen.queryByRole('combobox') ||
    document.querySelector('[aria-haspopup="listbox"]') ||
    document.querySelector('#share-menu-COL001-main-button') ||
    document.querySelector('button');
  fireEvent.click(trigger);
}

beforeEach(() => {
  apiFetch.mockClear();
  apiFetch.mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ share_url: 'http://x/share/NEWTOKEN', share_token: 'NEWTOKEN' }),
  });
});

describe('ShareCollectionMenu revoke / rotate', () => {
  test('a PUBLIC collection offers no revoke/rotate (no token to pull back)', () => {
    render(<ShareCollectionMenu {...props} isPublic />);
    openMenu();
    expect(screen.queryByRole('option', { name: /stop sharing/i })).toBeNull();
    expect(screen.queryByRole('option', { name: /rotate link/i })).toBeNull();
  });

  test('revoking a PRIVATE share link confirms, then DELETEs the token', async () => {
    render(<ShareCollectionMenu {...props} isPublic={false} />);
    openMenu();
    fireEvent.click(screen.getByRole('option', { name: /stop sharing/i }));

    // Consequence confirm appears before any request fires.
    expect(screen.getByText(/the invite link stops working for everyone/i)).toBeInTheDocument();
    expect(apiFetch).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /^stop sharing$/i }));
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        '/api/v1/collections/COL001/share-link/',
        expect.objectContaining({ method: 'DELETE' })
      )
    );
  });

  test('rotating a PRIVATE share link POSTs rotate:true', async () => {
    render(<ShareCollectionMenu {...props} isPublic={false} />);
    openMenu();
    fireEvent.click(screen.getByRole('option', { name: /rotate link/i }));
    fireEvent.click(screen.getByRole('button', { name: /^rotate link$/i }));
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        '/api/v1/collections/COL001/share-link/',
        expect.objectContaining({ method: 'POST', body: JSON.stringify({ rotate: true }) })
      )
    );
  });

  test('cancelling the confirm fires no request at all', async () => {
    // The confirm is the only thing between a menu pick and an irreversible
    // change to a credential other people are holding. If Cancel still went
    // through, the dialog would be theatre.
    render(<ShareCollectionMenu {...props} isPublic={false} />);
    openMenu();
    fireEvent.click(screen.getByRole('option', { name: /stop sharing/i }));

    // The dialog offers Cancel twice — its own close button and the action row —
    // and either one must mean the same thing.
    const cancels = screen.getAllByRole('button', { name: /cancel/i });
    fireEvent.click(cancels[cancels.length - 1]);

    await waitFor(() =>
      expect(screen.queryByText(/the invite link stops working for everyone/i)).toBeNull()
    );
    expect(apiFetch).not.toHaveBeenCalled();
  });
});

/**
 * The two failures that matter here are not crashes — they are the UI saying a
 * credential was withdrawn when it was not.
 *
 * An owner who reads "link rotated" stops worrying about whoever they sent the
 * old link to. If the request actually failed, that old link still works and the
 * person still has access: the owner has been told they closed a door that is
 * standing open. Nothing else in this component is security-relevant in that way,
 * which is why these two get their own tests rather than a shared error case.
 */
describe('a failed revoke or rotate must not claim it worked', () => {
  test('a failed rotate reports the failure, and never says "rotated"', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 500, json: () => Promise.resolve({}) });
    render(<ShareCollectionMenu {...props} isPublic={false} />);
    openMenu();
    fireEvent.click(screen.getByRole('option', { name: /rotate link/i }));
    fireEvent.click(screen.getByRole('button', { name: /^rotate link$/i }));

    expect(await screen.findByText(/couldn't generate the invite link/i)).toBeInTheDocument();
    expect(screen.queryByText(/new link created/i)).toBeNull();
  });

  test('a failed revoke reports the failure, and never says the link is off', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 500, json: () => Promise.resolve({}) });
    render(<ShareCollectionMenu {...props} isPublic={false} />);
    openMenu();
    fireEvent.click(screen.getByRole('option', { name: /stop sharing/i }));
    fireEvent.click(screen.getByRole('button', { name: /^stop sharing$/i }));

    expect(await screen.findByText(/couldn't generate the invite link/i)).toBeInTheDocument();
    expect(screen.queryByText(/sharing stopped/i)).toBeNull();
  });
});

/* NOT tested here, and deliberately left so rather than left flaky: that
   `ensureShareUrl` caches its answer in a ref, so a second share action reuses
   the link instead of POSTing again (which, for a PRIVATE collection, mints a
   token). Exercising it needs the HDS Select menu **opened twice in one test**,
   and that cannot be driven in this harness — the second open never populates
   the listbox once several renders have happened in the same file, whether the
   query is scoped to the container, awaited via findByRole, given its own
   collection code, or run after wiping document.body between tests. A test that
   only passes when run alone would certify nothing and cost the next person the
   same hour. The behaviour is visible in the browser and cheap to check by hand:
   open the menu, copy the link, reopen it, copy again — one request in the
   network panel, and the same token both times. */

/**
 * The other half of this menu — the one that actually hands the link over — had
 * no tests at all: `ensureShareUrl` and the four deliveries behind it. The
 * revoke/rotate pair above is guarded because a false success there tells an
 * owner they closed a door that is standing open; these carry two risks of
 * their own. A PUBLIC collection must not be given a bearer token it has no way
 * to take back, and a delivery that silently failed leaves the owner believing
 * a link is on its way to somebody who never got one.
 */
describe('handing the link over', () => {
  let originalLocation;
  let openSpy;

  beforeEach(() => {
    originalLocation = window.location;
    // A plain object, so `mailto:` is recorded instead of navigating jsdom.
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { href: '', origin: 'http://localhost:3000' },
    });
    openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn(() => Promise.resolve()) },
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
    vi.restoreAllMocks();
  });

  function pick(name) {
    openMenu();
    fireEvent.click(screen.getByRole('option', { name }));
  }

  test('a PUBLIC group is shared by its own address, and mints no token', async () => {
    // Anyone can read it without an account, so there is nothing to gate — and
    // a share token here would be a credential in the wild that this menu
    // deliberately offers no way to pull back (PUBLIC hides rotate/revoke).
    render(<ShareCollectionMenu {...props} isPublic />);

    pick('Copy invite link');

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        'http://localhost:3000/collections/COL001'
      )
    );
    expect(apiFetch).not.toHaveBeenCalled();
  });

  test('a PRIVATE group hands out the token the server minted', async () => {
    render(<ShareCollectionMenu {...props} isPublic={false} />);

    pick('Copy invite link');

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('http://x/share/NEWTOKEN')
    );
    expect(apiFetch).toHaveBeenCalledWith(
      '/api/v1/collections/COL001/share-link/',
      expect.objectContaining({ method: 'POST' })
    );
    expect(await screen.findByText(/copied to clipboard/i)).toBeInTheDocument();
  });

  test('a clipboard that refuses is never reported as a copy', async () => {
    // It refuses for real reasons — no permission, an insecure context, a
    // browser that wants a gesture it didn't see. The owner then pastes
    // whatever was there before into a message to a friend.
    navigator.clipboard.writeText.mockRejectedValue(new Error('denied'));
    render(<ShareCollectionMenu {...props} isPublic={false} />);

    pick('Copy invite link');

    expect(await screen.findByText(/couldn't copy the link/i)).toBeInTheDocument();
    expect(screen.queryByText(/copied to clipboard/i)).toBeNull();
  });

  test('a link that cannot be minted shares nothing at all', async () => {
    // Not merely "shows an error": the mail draft must not open with a blank or
    // stale link in it, which is the version the recipient would actually get.
    apiFetch.mockResolvedValue({ ok: false, status: 500, json: () => Promise.resolve({}) });
    render(<ShareCollectionMenu {...props} isPublic={false} />);

    pick('Email');

    expect(await screen.findByText(/couldn't generate the invite link/i)).toBeInTheDocument();
    expect(window.location.href).toBe('');
    expect(openSpy).not.toHaveBeenCalled();
  });

  test('the email draft carries the link and names the collection', async () => {
    render(<ShareCollectionMenu {...props} isPublic={false} />);

    pick('Email');

    await waitFor(() => expect(window.location.href).toMatch(/^mailto:\?subject=/));
    const draft = decodeURIComponent(window.location.href);
    expect(draft).toContain('http://x/share/NEWTOKEN');
    expect(draft).toContain('My Collection');
  });

  test('the WhatsApp hand-off carries the link and cannot reach back', async () => {
    // `noopener` is the load-bearing argument: without it the opened page gets a
    // handle on this one through `window.opener`.
    render(<ShareCollectionMenu {...props} isPublic={false} />);

    pick('WhatsApp');

    await waitFor(() => expect(openSpy).toHaveBeenCalled());
    const [url, target, features] = openSpy.mock.calls[0];
    expect(decodeURIComponent(url)).toContain('http://x/share/NEWTOKEN');
    expect(target).toBe('_blank');
    expect(features).toBe('noopener,noreferrer');
  });

  test('the QR encodes the invite link, and prints it underneath', async () => {
    render(<ShareCollectionMenu {...props} isPublic={false} />);

    pick('QR code');

    // What the camera would read …
    expect(await screen.findByTestId('qr')).toHaveAttribute(
      'data-value',
      'http://x/share/NEWTOKEN'
    );
    // … and what the person holding the phone up can check against it.
    expect(screen.getByText('http://x/share/NEWTOKEN')).toBeInTheDocument();
  });
});

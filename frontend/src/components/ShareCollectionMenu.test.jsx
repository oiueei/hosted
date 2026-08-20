import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, test, expect, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })),
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

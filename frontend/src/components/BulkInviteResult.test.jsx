import { render, screen } from '@testing-library/react';
import { describe, test, expect } from 'vitest';
import BulkInviteResult from './BulkInviteResult';

/**
 * The summary of a batch of invitations, shared by the CSV tool and by the invitations
 * field of `/invites` when it holds several addresses (G6, CA 2026-10-05).
 * `test/bulkInviteCsv.test.jsx` and `pages/ManageInvitesPage.test.jsx` pin it through
 * their own flows; these pin the component by itself.
 */
describe('BulkInviteResult', () => {
  test('with no result it is an empty live region, there already for what comes', () => {
    const { container } = render(<BulkInviteResult result={null} />);

    const region = container.querySelector('[role="status"]');
    expect(region).not.toBeNull();
    expect(region).toBeEmptyDOMElement();
  });

  test('says how many were invited, and nothing about skipped when none were', () => {
    render(<BulkInviteResult result={{ invited: 3, skipped: [] }} />);

    expect(screen.getByText('3 invitations sent.')).toBeInTheDocument();
    expect(screen.queryByText(/skipped/)).toBeNull();
    expect(screen.queryByRole('list')).toBeNull();
  });

  test('lists each skipped address with its reason in words', () => {
    render(
      <BulkInviteResult
        result={{
          invited: 1,
          skipped: [
            { email: 'bad', reason: 'invalid' },
            { email: 'dup@x.com', reason: 'duplicate' },
            { email: 'ana@x.com', reason: 'already_member' },
            { email: 'pen@x.com', reason: 'already_invited' },
            { email: 'late@x.com', reason: 'daily_limit' },
          ],
        }}
      />
    );

    expect(screen.getByText('5 skipped:')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      'bad — invalid email',
      'dup@x.com — duplicate',
      'ana@x.com — already a member',
      'pen@x.com — already invited',
      'late@x.com — daily invitation limit reached',
    ]);
  });

  test('a reason it does not know reads as an invalid address', () => {
    render(
      <BulkInviteResult result={{ invited: 0, skipped: [{ email: 'x@y.com', reason: '??' }] }} />
    );

    expect(screen.getByText('x@y.com — invalid email')).toBeInTheDocument();
  });

  test('nobody invited is a plain (info) notice, somebody invited a success one', () => {
    // HDS gives the default type no class of its own and a success one `--success`.
    const { container, rerender } = render(
      <BulkInviteResult result={{ invited: 0, skipped: [] }} />
    );
    const notice = () => container.querySelector('section');

    expect(notice().className).not.toMatch(/success|error|alert/);
    rerender(<BulkInviteResult result={{ invited: 2, skipped: [] }} />);
    expect(notice().className).toMatch(/success/);
  });
});

import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation, useNavigate } from 'react-router';
import { describe, test, expect } from 'vitest';
import { useCollectionBase, useCanonicalCollectionPath } from './useCollectionBase';

function Where() {
  const { pathname, search, hash, state } = useLocation();
  return <p data-testid="where">{`${pathname}${search}${hash}|${state?.headline ?? ''}`}</p>;
}

function Page({ kind }) {
  useCanonicalCollectionPath(kind);
  return <Where />;
}

function Base({ kind }) {
  return <p data-testid="base">{useCollectionBase('AbC123', kind)}</p>;
}

const at = (entry, element) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="*" element={element} />
      </Routes>
    </MemoryRouter>
  );

describe('useCollectionBase', () => {
  test.each([
    ['/stall/AbC123/add', '/stall/AbC123'],
    ['/library/AbC123/things/X/edit', '/library/AbC123'],
    ['/shed/AbC123', '/shed/AbC123'],
    ['/collections/AbC123/leave', '/collections/AbC123'],
    ['/things/X/edit', '/collections/AbC123'],
  ])('a page at %s links the group at %s', (entry, expected) => {
    at(entry, <Base />);
    expect(screen.getByTestId('base')).toHaveTextContent(expected);
  });

  test('the collection’s own kind wins over where the reader happened to arrive', () => {
    at('/collections/AbC123/edit', <Base kind="LIBRARY" />);
    expect(screen.getByTestId('base')).toHaveTextContent('/library/AbC123');
  });
});

describe('useCanonicalCollectionPath', () => {
  test('replaces the entry, so Back does not return to the address it corrected', () => {
    function WithBack() {
      const navigate = useNavigate();
      return (
        <>
          <Page kind="LIBRARY" />
          <button onClick={() => navigate(-1)}>back</button>
        </>
      );
    }
    render(
      <MemoryRouter initialEntries={['/me', '/collections/AbC123']} initialIndex={1}>
        <Routes>
          <Route path="*" element={<WithBack />} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByTestId('where')).toHaveTextContent('/library/AbC123');

    screen.getByRole('button', { name: 'back' }).click();

    return waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/me'));
  });

  test('moves the old address to the kind’s, keeping the query, the hash and the state', () => {
    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/collections/AbC123/join',
            search: '?thing=XyZ789',
            hash: '#a',
            state: { headline: 'Tools' },
          },
        ]}
      >
        <Routes>
          <Route path="*" element={<Page kind="LIBRARY" />} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByTestId('where')).toHaveTextContent(
      '/library/AbC123/join?thing=XyZ789#a|Tools'
    );
  });

  test('moves a collection opened under the wrong kind’s prefix', () => {
    at('/stall/AbC123/things/XyZ789', <Page kind="LIBRARY" />);
    expect(screen.getByTestId('where')).toHaveTextContent('/library/AbC123/things/XyZ789');
  });

  test.each([
    ['/library/AbC123', 'LIBRARY'],
    ['/stall/AbC123', undefined],
    ['/stall/AbC123', ''],
    ['/things/XyZ789', 'LIBRARY'],
  ])('leaves %s alone for kind %s', (entry, kind) => {
    at(entry, <Page kind={kind} />);
    expect(screen.getByTestId('where')).toHaveTextContent(entry);
  });
});

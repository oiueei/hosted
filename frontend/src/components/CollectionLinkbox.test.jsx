import { render, screen, fireEvent, createEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { describe, test, expect } from 'vitest';
import CollectionLinkbox from './CollectionLinkbox';

const collection = {
  code: 'COL001',
  headline: 'Kitchen Collection',
  thumbnail_url: 'https://bucket.example.com/oiueei/collections/cover.jpg',
  things: [{ code: 'THG001' }, { code: 'THG002' }],
  invites: [{ code: 'INV001' }],
};

describe('CollectionLinkbox', () => {
  test('renders no thumbnail, even when the collection has one (S8: full-width rows, no image)', () => {
    const { container } = render(
      <MemoryRouter>
        <CollectionLinkbox collection={collection} showInfo />
      </MemoryRouter>
    );
    expect(container.querySelector('img')).toBeNull();
  });

  test('still exposes the headline, counts, and a link to the collection', () => {
    render(
      <MemoryRouter>
        <CollectionLinkbox collection={collection} showInfo />
      </MemoryRouter>
    );
    expect(screen.getByText('Kitchen Collection')).toBeInTheDocument();
    expect(screen.getByText(/2.*·.*1/)).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', '/collections/COL001');
  });

  test('a headline written once per language reads as words, never as raw JSON (O6)', () => {
    // The test i18n mock runs in English, so the English text is what shows.
    const bilingual = {
      ...collection,
      headline: '{"es": "Las cosas de mamá", "ca": "Les coses de mama", "en": "Mum\'s things"}',
    };
    render(
      <MemoryRouter>
        <CollectionLinkbox collection={bilingual} showInfo />
      </MemoryRouter>
    );
    expect(screen.getByText("Mum's things")).toBeInTheDocument();
    expect(screen.queryByText(/\{"es"/)).toBeNull();
  });

  test('clicking navigates in-app instead of letting the browser follow the href', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<CollectionLinkbox collection={collection} showInfo />} />
          <Route path="/collections/:code" element={<p>Collection page</p>} />
        </Routes>
      </MemoryRouter>
    );

    // The `href` is real so the row is a proper link (middle-click, "open in new
    // tab", and a screen reader's link list all need it), but the handler must
    // `preventDefault` and route client-side — otherwise every collection row is
    // a full page reload, which on a mid-range phone is the whole bundle again
    // (DESIGN §7).
    const link = screen.getByRole('link');
    const click = createEvent.click(link);
    fireEvent(link, click);

    // Asserted on the event itself, because jsdom never follows an href: without
    // this, dropping `preventDefault` looks identical to keeping it, and the
    // full-reload regression would ship green.
    expect(click.defaultPrevented).toBe(true);
    expect(screen.getByText('Collection page')).toBeInTheDocument();
  });

  test('the profile grid omits the counts line the Home grids show', () => {
    render(
      <MemoryRouter>
        <CollectionLinkbox collection={collection} />
      </MemoryRouter>
    );

    // `showInfo` defaults to false, and the counts must then be absent rather
    // than rendered empty — the profile grid passes collections that carry no
    // `things`/`invites` arrays at all, so reading them would throw.
    expect(screen.getByText('Kitchen Collection')).toBeInTheDocument();
    expect(screen.queryByText(/2.*·.*1/)).toBeNull();
  });

  test('a collection with no counts loaded renders rather than throwing', () => {
    const bare = { code: 'COL002', headline: 'Just a headline' };

    render(
      <MemoryRouter>
        <CollectionLinkbox collection={bare} />
      </MemoryRouter>
    );

    expect(screen.getByText('Just a headline')).toBeInTheDocument();
  });
});

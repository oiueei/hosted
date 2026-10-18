import { render, fireEvent } from '@testing-library/react';
import { vi, describe, test, expect } from 'vitest';
import CollectionAdvancedFields from './CollectionAdvancedFields';

const noop = () => {};
const base = {
  idPrefix: 'edit-collection',
  colors: { color_01: 'bus', color_04: 'black', color_06: 'white' },
  isReservations: false,
  hasRequestPage: false,
  tags: [],
  setTags: noop,
  reservationRules: {},
  rentalRules: {
    rentalDurations: [],
    setRentalDurations: noop,
    rentalWeekdays: [],
    setRentalWeekdays: noop,
    depositPolicy: '',
    setDepositPolicy: noop,
  },
  closedDates: '',
  setClosedDates: noop,
  requestInfo: '',
  setRequestInfo: noop,
  emailNote: '',
  setEmailNote: noop,
  homePage: '',
  setHomePage: noop,
  digestFrequency: 'WEEKLY',
  setDigestFrequency: noop,
  language: 'en',
  setLanguage: noop,
  thumbnail: '',
  setThumbnail: noop,
  setWelcomeDoc: noop,
};

const idsOf = (container) =>
  [...container.querySelectorAll('[id]')]
    .map((e) => e.id)
    .filter((id) => id.startsWith('edit-') || id.startsWith('create-'));

describe('CollectionAdvancedFields', () => {
  test('a stall has the fields every collection has, and none of the request page’s', () => {
    const { container } = render(<CollectionAdvancedFields {...base} />);

    for (const field of [
      'email-note',
      'home-page',
      'digest',
      'language',
      'thumbnail',
      'welcome-doc',
    ]) {
      expect(container.querySelector(`#edit-collection-${field}`), field).not.toBeNull();
    }
    expect(container.querySelector('#edit-collection-closed-dates')).toBeNull();
    expect(container.querySelector('#edit-collection-request-info')).toBeNull();
    expect(container.querySelector('#edit-collection-deposit-policy')).toBeNull();
  });

  test('a library adds the closed days, the note before asking and the deposit policy', () => {
    const { container } = render(<CollectionAdvancedFields {...base} hasRequestPage />);

    for (const field of ['closed-dates', 'request-info', 'deposit-policy']) {
      expect(container.querySelector(`#edit-collection-${field}`), field).not.toBeNull();
    }
  });

  test('the id prefix names every field, so the two forms do not share ids', () => {
    const { container } = render(
      <CollectionAdvancedFields {...base} idPrefix="create-collection" hasRequestPage />
    );

    const ids = idsOf(container);
    expect(ids.length).toBeGreaterThan(8);
    expect(ids.every((id) => id.startsWith('create-collection-'))).toBe(true);
  });

  test('the slot under the email note is rendered there, and only there', () => {
    const { container, getByText } = render(
      <CollectionAdvancedFields {...base} afterEmailNote={<button>Test slot</button>} />
    );

    const block = container
      .querySelector('#edit-collection-email-note')
      .closest('.form-grid > div');
    expect(block).toContainElement(getByText('Test slot'));
    expect(
      container.querySelector('#edit-collection-home-page').closest('.form-grid > div')
    ).not.toBe(block);
  });

  test('a saved photo and welcome document are handed to their uploads', () => {
    const { container } = render(
      <CollectionAdvancedFields
        {...base}
        thumbnail="k"
        thumbnailUrl="http://x/thumb.png"
        welcomeDocUrl="http://x/doc.pdf"
      />
    );

    expect(container.querySelector('img[src="http://x/thumb.png"]')).not.toBeNull();
    expect(container.querySelector('a[href="http://x/doc.pdf"]')).not.toBeNull();
  });

  test('typing in the home page reports the new text', () => {
    const setHomePage = vi.fn();
    const { container } = render(<CollectionAdvancedFields {...base} setHomePage={setHomePage} />);

    fireEvent.change(container.querySelector('#edit-collection-home-page'), {
      target: { value: 'https://x.example/' },
    });

    expect(setHomePage).toHaveBeenCalledWith('https://x.example/');
  });
});

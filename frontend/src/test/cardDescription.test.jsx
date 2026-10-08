import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect } from 'vitest';
import { rulesFor } from './cssRules';

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(() => Promise.resolve({ ok: true, status: 200, json: async () => ({}) })),
  extractApiError: vi.fn(() => Promise.resolve('')),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import MarkdownText, { markdownToHtml } from '../components/MarkdownText';
import ThingLinkbox from '../components/ThingLinkbox';

const DESCRIPTION = '# Normas\n**Importante**: trae *tu* caja. [más](https://example.com)';

const thing = {
  code: 'THG001',
  type: 'GIFT_THING',
  headline: 'Lamp',
  description: DESCRIPTION,
  status: 'ACTIVE',
  owner: 'OWNER1',
  owner_name: 'Lele',
  thumbnail_url: '',
  gallery_urls: [],
  transfer_count: 0,
};

const renderCard = () =>
  render(
    <MemoryRouter>
      <ThingLinkbox thing={thing} userCode="GUEST1" onUpdateThing={() => {}} />
    </MemoryRouter>
  );

describe('the description on a thing’s card', () => {
  test('is a couple of quiet lines: titles and bold read as plain text', () => {
    renderCard();

    const description = document.querySelector('.thing-card-description');
    expect(description.querySelector('h2, h3, h4, h5, strong')).toBeNull();
    expect(description).toHaveTextContent('Normas');
    expect(description).toHaveTextContent('Importante: trae tu caja.');
    expect(description).not.toHaveTextContent('#');
  });

  test('keeps italics and links', () => {
    renderCard();

    const description = document.querySelector('.thing-card-description');
    expect(description.querySelector('em')).toHaveTextContent('tu');
    expect(screen.getByRole('link', { name: 'más' })).toHaveAttribute(
      'href',
      'https://example.com'
    );
  });

  test('the card has its own <h3>, and the description adds none to the outline', () => {
    renderCard();

    expect(screen.getAllByRole('heading')).toHaveLength(1);
    expect(screen.getByRole('heading', { name: 'Lamp' }).tagName).toBe('H3');
  });

  test('anywhere else the same text keeps its headings and bold', () => {
    const { container } = render(<MarkdownText text={DESCRIPTION} />);

    expect(container.querySelector('h3')).toHaveTextContent('Normas');
    expect(container.querySelector('strong')).toHaveTextContent('Importante');
    expect(markdownToHtml(DESCRIPTION)).toContain('<strong>');
  });

  test('a list on the card loses its bold too', () => {
    const out = markdownToHtml('- **uno**\n- dos', 3, 'card');
    expect(out).toBe('<ul><li>uno</li><li>dos</li></ul>');
  });

  test('is clamped to two lines', () => {
    const body = rulesFor('.thing-card-description').join('');
    expect(body).toMatch(/-webkit-line-clamp:\s*2\b/);
  });
});

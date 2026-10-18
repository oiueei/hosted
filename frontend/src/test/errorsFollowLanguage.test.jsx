import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

const apiFetchMock = vi.fn();
vi.mock('../services/api', () => ({
  apiFetch: (...args) => apiFetchMock(...args),
  extractApiError: vi.fn(() => Promise.resolve('')),
}));

import i18n from '../i18n';
import DataExportPage from '../pages/DataExportPage';
import TagInput from '../components/TagInput';
import { translateError, errorKey } from '../utils/errorKey';
import { switchLanguage } from './settle';
import es from '../i18n/locales/es.json';

/**
 * An error on screen is held as its key (and parameters) and translated where it
 * is painted, so changing the language leaves it in the new one. It used to be the
 * sentence in the language current when it failed.
 */
beforeEach(async () => {
  localStorage.clear();
  apiFetchMock.mockReset();
  await switchLanguage(i18n, 'en');
});
afterEach(async () => {
  await switchLanguage(i18n, 'en');
});

describe('an error already on screen follows the language', () => {
  test('a page’s: the connection error of the data export', async () => {
    apiFetchMock.mockRejectedValue(new Error('offline'));
    render(
      <MemoryRouter>
        <DataExportPage />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole('button', { name: /download my data/i }));
    expect(await screen.findByText('Connection error.')).toBeInTheDocument();

    await switchLanguage(i18n, 'es');

    expect(screen.getByText(es.common.connectionError)).toBeInTheDocument();
    expect(screen.queryByText('Connection error.')).toBeNull();
  });

  test('a field’s, with its parameter: a tag label that is too long', async () => {
    render(<TagInput tags={[]} onChange={() => {}} label="Tags" placeholder="Add a tag" />);
    fireEvent.change(screen.getByPlaceholderText('Add a tag'), {
      target: { value: 'x'.repeat(33) },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(
      await screen.findByText('One label is over 32 characters (per language).')
    ).toBeInTheDocument();

    await switchLanguage(i18n, 'es');

    expect(screen.getByText(es.tags.tooLong.replace('{{limit}}', '32'))).toBeInTheDocument();
  });
});

describe('translateError', () => {
  const t = (key, params) => `${key}|${JSON.stringify(params ?? null)}`;

  test('translates a key with its parameters', () => {
    expect(translateError(t, errorKey('a.b', { max: 3 }))).toBe('a.b|{"max":3}');
  });

  test('leaves the server’s own text as it is, and nothing as nothing', () => {
    expect(translateError(t, 'Slot already taken.')).toBe('Slot already taken.');
    expect(translateError(t, null)).toBe('');
    expect(translateError(t, '')).toBe('');
  });
});

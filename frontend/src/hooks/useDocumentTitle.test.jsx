import { renderHook } from '@testing-library/react';
import { describe, test, expect, beforeEach } from 'vitest';
import useDocumentTitle from './useDocumentTitle';

beforeEach(() => {
  document.title = 'Before';
});

describe('useDocumentTitle', () => {
  test('puts the title on the tab', () => {
    renderHook(() => useDocumentTitle('Home — OIUEEI'));

    expect(document.title).toBe('Home — OIUEEI');
  });

  test('follows the title when it changes', () => {
    const { rerender } = renderHook(({ title }) => useDocumentTitle(title), {
      initialProps: { title: 'Loading — OIUEEI' },
    });
    expect(document.title).toBe('Loading — OIUEEI');

    rerender({ title: 'The street — OIUEEI' });

    expect(document.title).toBe('The street — OIUEEI');
  });

  test.each([
    ['empty', ''],
    ['undefined', undefined],
    ['null', null],
  ])('a %s title leaves the tab as it was', (_, title) => {
    renderHook(() => useDocumentTitle(title));

    expect(document.title).toBe('Before');
  });
});

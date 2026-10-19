import { describe, test, expect, vi } from 'vitest';
import { fetchAllPages } from './fetchAllPages';

const page = (results, next = null) =>
  Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ results, next }) });
const refused = () => Promise.resolve({ ok: false, status: 500, json: async () => ({}) });

describe('fetchAllPages', () => {
  test('follows next to the end, keeping the order, and strips the origin from it', async () => {
    const apiFetch = vi
      .fn()
      .mockReturnValueOnce(page([1, 2], 'https://x.test/api/v1/things/?page=2&page_size=2'))
      .mockReturnValueOnce(page([3, 4], 'http://x.test/api/v1/things/?page=3&page_size=2'))
      .mockReturnValueOnce(page([5]));
    const out = await fetchAllPages(apiFetch, '/api/v1/things/?page_size=2');
    expect(out).toEqual({ rows: [1, 2, 3, 4, 5], complete: true });
    expect(apiFetch.mock.calls.map((c) => c[0])).toEqual([
      '/api/v1/things/?page_size=2',
      '/api/v1/things/?page=2&page_size=2',
      '/api/v1/things/?page=3&page_size=2',
    ]);
  });

  test('a later page that is refused leaves what was read, flagged incomplete', async () => {
    const apiFetch = vi
      .fn()
      .mockReturnValueOnce(page([1, 2], 'https://x.test/p2'))
      .mockReturnValueOnce(refused());
    expect(await fetchAllPages(apiFetch, '/p1')).toEqual({ rows: [1, 2], complete: false });
  });

  test('a later page whose request throws leaves what was read, flagged incomplete', async () => {
    const apiFetch = vi
      .fn()
      .mockReturnValueOnce(page([1], 'https://x.test/p2'))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'));
    expect(await fetchAllPages(apiFetch, '/p1')).toEqual({ rows: [1], complete: false });
  });

  test('a first page that throws rejects, so the caller keeps its own failure path', async () => {
    const apiFetch = vi.fn().mockRejectedValueOnce(new TypeError('Failed to fetch'));
    await expect(fetchAllPages(apiFetch, '/p1')).rejects.toThrow('Failed to fetch');
  });

  test('a first page that is refused is empty and incomplete', async () => {
    const apiFetch = vi.fn().mockReturnValueOnce(refused());
    expect(await fetchAllPages(apiFetch, '/p1')).toEqual({ rows: [], complete: false });
  });

  test('a list that never ends stops at the page cap, flagged incomplete', async () => {
    const apiFetch = vi.fn(() => page([1], 'https://x.test/again'));
    const out = await fetchAllPages(apiFetch, '/p1');
    expect(out.complete).toBe(false);
    expect(out.rows).toHaveLength(50);
    expect(apiFetch).toHaveBeenCalledTimes(50);
  });
});

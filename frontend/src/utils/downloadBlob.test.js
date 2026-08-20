import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

import downloadBlob from './downloadBlob';

/**
 * The file-download dance, extracted so the pages that offer a file stop each
 * keeping their own copy of it.
 *
 * Both failures it guards are invisible while the download itself works, which
 * is why a copy that got them wrong could live for months: a blob whose object
 * URL is never revoked stays in memory until the tab closes, and an anchor left
 * behind in the body is a focusable element sitting between the page's real
 * controls, reachable by Tab and announced by a screen reader.
 */

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => 'blob:fake');
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  delete URL.createObjectURL;
  delete URL.revokeObjectURL;
  document.body.innerHTML = '';
});

describe('downloadBlob', () => {
  test('offers the bytes under the name the caller asked for', () => {
    const clicked = [];
    // jsdom implements click() but navigating to a blob: URL is not something it
    // can do, so the anchor's own click is what gets observed here.
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(function record() {
        clicked.push({ href: this.href, download: this.download, inDocument: this.isConnected });
      });

    const blob = new Blob(['a,b\n1,2\n'], { type: 'text/csv' });
    downloadBlob(blob, 'ABC123-stats.csv');

    expect(URL.createObjectURL).toHaveBeenCalledWith(blob);
    expect(clicked).toHaveLength(1);
    expect(clicked[0].download).toBe('ABC123-stats.csv');
    expect(clicked[0].href).toBe('blob:fake');
    // Firefox ignores a click on a detached anchor, so it has to be in the
    // document at the moment it fires — not merely created.
    expect(clicked[0].inDocument).toBe(true);

    clickSpy.mockRestore();
  });

  test('leaves nothing behind: no anchor in the body, no unrevoked URL', () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    downloadBlob(new Blob(['{}'], { type: 'application/json' }), 'oiueei-ABC123.json');

    expect(document.querySelectorAll('a[download]')).toHaveLength(0);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:fake');

    clickSpy.mockRestore();
  });
});

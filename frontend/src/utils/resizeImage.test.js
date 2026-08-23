import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';
import { resizeImage } from './resizeImage';

// jsdom decodes no images and implements no canvas, so both are stubbed here and
// only the scaling maths + File plumbing are actually under test.
//
// What these protect since the move off Cloudinary: delivery used to re-encode
// (`f_auto,q_auto`), so whatever went up, a modern browser was sent WebP. An
// object store serves the bytes it was given, which makes the encode this
// function does the only one there is.
let canvases;
// Lets a test make the encoder answer with something other than what was asked
// for — or with nothing — which is exactly what `toBlob` is allowed to do.
let canvasBlobType;

function stubImage({ width, height, fail = false }) {
  class FakeImage {
    constructor() {
      this.width = width;
      this.height = height;
    }
    set src(value) {
      this._src = value;
      // A real decode never resolves on the setter's own stack.
      queueMicrotask(() => (fail ? this.onerror() : this.onload()));
    }
    get src() {
      return this._src;
    }
  }
  vi.stubGlobal('Image', FakeImage);
}

const jpeg = () => new File(['bytes'], 'photo.jpg', { type: 'image/jpeg' });

beforeEach(() => {
  canvases = [];
  canvasBlobType = undefined;
  URL.createObjectURL = vi.fn(() => 'blob:mock-url');
  URL.revokeObjectURL = vi.fn();
  const realCreateElement = document.createElement.bind(document);
  vi.spyOn(document, 'createElement').mockImplementation((tag, ...rest) => {
    if (tag !== 'canvas') return realCreateElement(tag, ...rest);
    const canvas = {
      width: 0,
      height: 0,
      getContext: vi.fn(() => ({ drawImage: vi.fn() })),
      toBlob: vi.fn((cb, type) => {
        const actual = canvasBlobType === undefined ? type : canvasBlobType;
        cb(actual === null ? null : new Blob(['resized'], { type: actual }));
      }),
    };
    canvases.push(canvas);
    return canvas;
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  delete URL.createObjectURL;
  delete URL.revokeObjectURL;
});

describe('resizeImage', () => {
  test('re-encodes a small image instead of passing it through', async () => {
    // It used to come back untouched, which was right while Cloudinary
    // re-encoded on delivery. Now the stored object is the delivered object, so
    // a 900px PNG passed through would genuinely be served as that PNG.
    stubImage({ width: 800, height: 600 });
    const file = jpeg();

    const out = await resizeImage(file);

    expect(out).not.toBe(file);
    expect(out.type).toBe('image/webp');
    expect(out.name).toBe('photo.webp');
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url');
  });

  test('a small image keeps its own dimensions — re-encoded, not upscaled', async () => {
    stubImage({ width: 800, height: 600 });

    await resizeImage(jpeg());

    expect(canvases[0]).toMatchObject({ width: 800, height: 600 });
  });

  test('an image exactly at the cap is not scaled either way', async () => {
    stubImage({ width: 1216, height: 1216 });

    await resizeImage(jpeg());

    expect(canvases[0]).toMatchObject({ width: 1216, height: 1216 });
  });

  test('scales a landscape image to 1216 on its longest side, keeping the ratio', async () => {
    stubImage({ width: 2432, height: 1216 });

    const out = await resizeImage(jpeg());

    expect(canvases[0]).toMatchObject({ width: 1216, height: 608 });
    expect(out).toBeInstanceOf(File);
    expect(out.name).toBe('photo.webp');
    expect(out.type).toBe('image/webp');
  });

  test('asks the canvas for WebP', async () => {
    stubImage({ width: 2432, height: 1216 });

    await resizeImage(jpeg());

    expect(canvases[0].toBlob).toHaveBeenCalledWith(expect.any(Function), 'image/webp', 0.82);
  });

  test('reports whatever the encoder actually produced, not what it asked for', async () => {
    // `toBlob` falls back to PNG where WebP encoding is missing, and says nothing.
    // The caller signs this type into the upload, so claiming WebP here would
    // have the store serve a PNG announced as something else.
    stubImage({ width: 2432, height: 1216 });
    canvasBlobType = 'image/png';

    const out = await resizeImage(jpeg());

    expect(out.type).toBe('image/png');
    expect(out.name).toBe('photo.png');
  });

  test('falls back to the original when the canvas encodes nothing at all', async () => {
    stubImage({ width: 2432, height: 1216 });
    canvasBlobType = null;
    const file = jpeg();

    // A real image the browser cannot encode is still worth uploading; failing
    // here would take the whole form down over a missing codec.
    await expect(resizeImage(file)).resolves.toBe(file);
  });

  test('caps a portrait image on its height instead', async () => {
    stubImage({ width: 1000, height: 4000 });

    await resizeImage(jpeg());

    expect(canvases[0]).toMatchObject({ width: 304, height: 1216 });
  });

  test('honours a caller-supplied maxPx', async () => {
    stubImage({ width: 1000, height: 500 });

    await resizeImage(jpeg(), 500);

    expect(canvases[0]).toMatchObject({ width: 500, height: 250 });
  });

  // Anything the browser can't decode (a PDF picked by mistake, a corrupt file)
  // must come back untouched rather than reject — the caller uploads it as-is.
  test('returns the original when the browser cannot decode it', async () => {
    stubImage({ width: 0, height: 0, fail: true });
    const file = new File(['%PDF-1.4'], 'not-a-photo.pdf', { type: 'application/pdf' });

    await expect(resizeImage(file)).resolves.toBe(file);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url');
  });
});

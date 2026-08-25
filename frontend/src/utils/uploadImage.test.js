import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../services/api', () => ({ apiFetch: vi.fn() }));
// The scaling and the re-encode are covered by resizeImage.test.js; here it only
// has to run first and hand its output to the upload.
vi.mock('./resizeImage', () => ({ resizeImage: vi.fn() }));

import { apiFetch } from '../services/api';
import { resizeImage } from './resizeImage';
import { uploadImage, IMAGE_MAX_BYTES, UploadTooLargeError } from './uploadImage';

// What the server hands back (core/views/upload.py). Everything that constrains
// the upload — key, type, cache policy, byte length — is already inside `url`'s
// signature; the client's job is to send exactly what it was told to.
const TICKET = {
  url: 'https://bucket.fsn1.example-storage.com/oiueei/things/abc?X-Amz-Signature=sig',
  method: 'PUT',
  headers: {
    'x-amz-acl': 'public-read',
    'Content-Type': 'image/webp',
    'Cache-Control': 'public, max-age=31536000, immutable',
  },
  key: 'oiueei/things/abc',
  public_url: 'https://bucket.fsn1.example-storage.com/oiueei/things/abc',
};

function jsonResponse(data, ok = true) {
  return { ok, status: ok ? 200 : 400, json: () => Promise.resolve(data) };
}

const photo = () => new File(['original bytes'], 'photo.jpg', { type: 'image/jpeg' });

let fetchMock;
let resized;

beforeEach(() => {
  vi.clearAllMocks();
  resized = new File(['smaller bytes'], 'photo.webp', { type: 'image/webp' });
  resizeImage.mockResolvedValue(resized);
  apiFetch.mockResolvedValue(jsonResponse(TICKET));
  // The store answers an empty body — there is nothing to read back from it.
  fetchMock = vi.fn(() => Promise.resolve({ ok: true, status: 200 }));
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('uploadImage', () => {
  test('resizes first, then PUTs the resized file with the headers it was given', async () => {
    const original = photo();

    const result = await uploadImage(original);

    expect(resizeImage).toHaveBeenCalledWith(original);

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe(TICKET.url);
    expect(options.method).toBe('PUT');
    expect(options.headers).toEqual(TICKET.headers);
    // The raw file is the body — not form-data, which is what the old
    // Cloudinary path sent and what the presigned URL would refuse.
    expect(options.body).toBe(resized);

    expect(result).toEqual({ publicId: TICKET.key, url: TICKET.public_url });
  });

  test('declares the type and length of what it is actually about to send', async () => {
    await uploadImage(photo());

    expect(apiFetch).toHaveBeenCalledWith('/api/v1/upload/ticket/', {
      method: 'POST',
      body: JSON.stringify({
        folder: 'oiueei/things',
        content_type: 'image/webp',
        content_length: resized.size,
      }),
    });
  });

  test('declares the resize output, never the original file', async () => {
    // The whole point of reading them off the resize result: the server signs
    // these two values, so declaring the original's would fail at the bucket.
    resized = new File(['x'], 'photo.png', { type: 'image/png' });
    resizeImage.mockResolvedValue(resized);

    await uploadImage(photo());

    const body = JSON.parse(apiFetch.mock.calls[0][1].body);
    expect(body.content_type).toBe('image/png');
    expect(body.content_length).toBe(resized.size);
  });

  test('asks for a ticket on the caller-chosen folder', async () => {
    await uploadImage(photo(), 'oiueei/users');

    expect(JSON.parse(apiFetch.mock.calls[0][1].body).folder).toBe('oiueei/users');
  });

  test('throws signature_failed and uploads nothing when the server refuses a ticket', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ detail: 'no' }, false));

    await expect(uploadImage(photo())).rejects.toThrow('signature_failed');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test('throws upload_failed when the store rejects the upload', async () => {
    // What a tampered length or type looks like from here: 403 from the bucket.
    fetchMock.mockResolvedValue({ ok: false, status: 403 });

    await expect(uploadImage(photo())).rejects.toThrow('upload_failed');
  });

  describe('the size a resize could not fix', () => {
    // `resizeImage` returns the original untouched when the browser cannot
    // decode it, which is the only realistic way something oversized reaches
    // the ticket call. The server would refuse it anyway (the cap is signed);
    // the point of failing here is that the person gets told what is wrong
    // instead of a generic "upload failed" after a pointless round trip.
    const oversized = () => {
      const file = new File(['x'], 'raw.tiff', { type: 'image/tiff' });
      Object.defineProperty(file, 'size', { value: IMAGE_MAX_BYTES + 1 });
      return file;
    };

    test('refuses it before asking for a ticket', async () => {
      resizeImage.mockResolvedValue(oversized());

      await expect(uploadImage(photo())).rejects.toBeInstanceOf(UploadTooLargeError);
      expect(apiFetch).not.toHaveBeenCalled();
      expect(fetchMock).not.toHaveBeenCalled();
    });

    test('judges the RESIZED file, not the original', async () => {
      // The regression that would matter: a 30 MB phone photo resizes to a few
      // hundred kilobytes and must upload. Checking the original would refuse
      // exactly the files this product is for.
      const huge = photo();
      Object.defineProperty(huge, 'size', { value: IMAGE_MAX_BYTES * 3 });

      await expect(uploadImage(huge)).resolves.toEqual({
        publicId: TICKET.key,
        url: TICKET.public_url,
      });
    });

    test('accepts a file exactly on the limit', async () => {
      // The cap is `>`, and it has to match the server's `<=` boundary
      // (core/views/upload.py) or the courtesy check refuses what the real one
      // allows.
      const exact = new File(['x'], 'edge.webp', { type: 'image/webp' });
      Object.defineProperty(exact, 'size', { value: IMAGE_MAX_BYTES });
      resizeImage.mockResolvedValue(exact);

      await expect(uploadImage(photo())).resolves.toHaveProperty('publicId', TICKET.key);
    });
  });
});

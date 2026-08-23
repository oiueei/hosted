import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../services/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '../services/api';
import { uploadPdf, PDF_MAX_BYTES } from './uploadPdf';

// Document-mode ticket (core/views/upload.py): the folder is forced server-side
// and the only content type it will sign is application/pdf.
const TICKET = {
  url: 'https://bucket.fsn1.example-storage.com/oiueei/documents/xyz?X-Amz-Signature=sig',
  method: 'PUT',
  headers: {
    'x-amz-acl': 'public-read',
    'Content-Type': 'application/pdf',
    'Cache-Control': 'public, max-age=31536000, immutable',
  },
  key: 'oiueei/documents/xyz',
  public_url: 'https://bucket.fsn1.example-storage.com/oiueei/documents/xyz',
};

function jsonResponse(data, ok = true) {
  return { ok, status: ok ? 200 : 400, json: () => Promise.resolve(data) };
}

const pdf = () => new File(['%PDF-1.4'], 'welcome.pdf', { type: 'application/pdf' });

let fetchMock;

beforeEach(() => {
  vi.clearAllMocks();
  apiFetch.mockResolvedValue(jsonResponse(TICKET));
  fetchMock = vi.fn(() => Promise.resolve({ ok: true, status: 200 }));
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('uploadPdf', () => {
  test('asks for a document ticket and PUTs the file unresized', async () => {
    const file = pdf();

    const result = await uploadPdf(file);

    expect(apiFetch).toHaveBeenCalledWith('/api/v1/upload/ticket/', {
      method: 'POST',
      body: JSON.stringify({
        folder: 'oiueei/documents',
        kind: 'document',
        content_type: 'application/pdf',
        content_length: file.size,
      }),
    });

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe(TICKET.url);
    expect(options.method).toBe('PUT');
    // A document is not a photo: the bytes that go up are the ones picked.
    expect(options.body).toBe(file);

    expect(result).toEqual({ publicId: TICKET.key, url: TICKET.public_url });
  });

  test('signs application/pdf, which is what makes it open in a viewer', async () => {
    // Emailed as a link and opened weeks later. Stored without this the object
    // is served as binary/octet-stream and the browser downloads it instead.
    await uploadPdf(pdf());

    expect(JSON.parse(apiFetch.mock.calls[0][1].body).content_type).toBe('application/pdf');
    expect(fetchMock.mock.calls[0][1].headers['Content-Type']).toBe('application/pdf');
  });

  test('the client cap matches the one the server signs', async () => {
    // PdfUpload refuses an oversized file before this runs, as a courtesy. The
    // real limit is DOCUMENT_MAX_BYTES in core/views/upload.py; if the two ever
    // disagree, one of them is lying to somebody.
    expect(PDF_MAX_BYTES).toBe(5 * 1024 * 1024);
  });

  test('throws signature_failed and uploads nothing when the server refuses a ticket', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ detail: 'no' }, false));

    await expect(uploadPdf(pdf())).rejects.toThrow('signature_failed');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test('throws upload_failed when the store rejects the upload', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 403 });

    await expect(uploadPdf(pdf())).rejects.toThrow('upload_failed');
  });
});

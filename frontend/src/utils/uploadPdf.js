import { apiFetch } from '../services/api';

// The collection welcome doc: PDF only, 5 MB. This check is now a courtesy
// rather than the cap — it exists so an oversized file is refused instantly,
// with a message next to the field, instead of after a round trip. The real
// limit is signed into the upload ticket by the server (`UploadTicketView`),
// where a client cannot skip it. Keep the two numbers equal.
export const PDF_MAX_BYTES = 5 * 1024 * 1024;

/**
 * Upload a PDF straight to object storage through a short-lived server-issued
 * ticket — the same path as `uploadImage`, with `kind: 'document'` so the ticket
 * only permits a PDF and the server forces the documents folder (S4). No resize:
 * a document is not a photo. Returns `{ publicId, url }`.
 */
export async function uploadPdf(file, folder = 'oiueei/documents') {
  const ticketRes = await apiFetch('/api/v1/upload/ticket/', {
    method: 'POST',
    body: JSON.stringify({
      folder,
      kind: 'document',
      // Signed exactly. This is what makes the bucket serve the document as
      // application/pdf, so the browser opens it in its viewer instead of
      // downloading it — the link in the welcome email is the whole point.
      content_type: 'application/pdf',
      content_length: file.size,
    }),
  });
  if (!ticketRes.ok) throw new Error('signature_failed');
  const { url, method, headers, key, public_url: publicUrl } = await ticketRes.json();

  const uploadRes = await fetch(url, { method, headers, body: file });
  if (!uploadRes.ok) throw new Error('upload_failed');

  return { publicId: key, url: publicUrl };
}

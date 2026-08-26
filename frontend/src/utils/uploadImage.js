import { apiFetch } from '../services/api';
import { resizeImage } from './resizeImage';

// Mirrors `IMAGE_MAX_BYTES` in `core/views/upload.py`, which is the one that is
// signed and therefore the one that counts.
export const IMAGE_MAX_BYTES = 10 * 1024 * 1024;

/**
 * "This particular file is too big" — as opposed to every other upload failure,
 * which the caller can only describe as "it didn't work".
 *
 * A named class rather than a string code so `instanceof` decides, and a typo in
 * a comparison is a crash at the point of the mistake rather than a wrong
 * message shown to somebody.
 */
export class UploadTooLargeError extends Error {
  constructor() {
    super('image_too_large');
    this.name = 'UploadTooLargeError';
  }
}

/**
 * Resize an image File client-side (≤1216px, WebP) and upload it straight to
 * object storage using a short-lived server-issued ticket. Returns
 * `{ publicId, url }` — `publicId` is the storage key to save on the model,
 * `url` is where it will be readable. Throws on ticket/upload failure.
 *
 * Extracted from the inline flow in ImageUpload / GalleryUpload so the CSV/ZIP
 * bulk import can reuse the exact same path.
 *
 * The binary never touches our server, exactly as before. What changed is where
 * the rules live: the server used to sign parameters that the client echoed back
 * to Cloudinary, and now it signs the URL itself. Key, folder, content type,
 * cache policy and byte length are all inside that signature, so the only upload
 * this ticket permits is the one that was asked for — a different file, a
 * different type or a different length is refused by the bucket, not by us.
 */
export async function uploadImage(original, folder = 'oiueei/things') {
  const file = await resizeImage(original);

  // Checked **after** the resize, never before it: a 30 MB photo from a phone
  // routinely lands in the hundreds of kilobytes once downscaled to 1216px and
  // encoded to WebP, so refusing on the original size would reject files that
  // upload perfectly. What gets here at full size is what `resizeImage` handed
  // back untouched — a format the browser could not decode.
  //
  // Like `PDF_MAX_BYTES`, this is a courtesy and not the cap: the real limit is
  // signed into the ticket by `UploadTicketView`, where a client cannot skip it.
  // Its job is to fail here, with a message that says what is wrong, instead of
  // after a round trip with a generic "upload failed". Keep the two numbers equal.
  if (file.size > IMAGE_MAX_BYTES) throw new UploadTooLargeError();

  const ticketRes = await apiFetch('/api/v1/upload/ticket/', {
    method: 'POST',
    body: JSON.stringify({
      folder,
      // Whatever the resize actually produced. `resizeImage` falls back to PNG
      // where WebP encoding isn't available and returns the original untouched
      // when it can't decode it, so this is read from the file rather than
      // assumed — a wrong type here is a 400 from our own server.
      content_type: file.type,
      content_length: file.size,
    }),
  });
  if (!ticketRes.ok) throw new Error('signature_failed');
  const { url, method, headers, key, public_url: publicUrl } = await ticketRes.json();

  // The file goes up as the raw body, not as form-data. Content-Length is signed
  // too but is absent from `headers`: the browser sets it from the body, and
  // JavaScript is not allowed to, which is what makes it unforgeable.
  const uploadRes = await fetch(url, { method, headers, body: file });
  if (!uploadRes.ok) throw new Error('upload_failed');

  // Nothing to read from the response: the store answers 200 with an empty body,
  // and the key was decided before the upload rather than returned by it.
  return { publicId: key, url: publicUrl };
}

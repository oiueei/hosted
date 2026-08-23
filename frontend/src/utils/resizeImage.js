const MAX_PX = 1216;
const OUTPUT_TYPE = 'image/webp';
const QUALITY = 0.82;

const EXTENSIONS = {
  'image/webp': 'webp',
  'image/png': 'png',
  'image/jpeg': 'jpg',
};

function renamed(name, type) {
  const extension = EXTENSIONS[type];
  if (!extension) return name;
  return `${name.replace(/\.[^.]+$/, '')}.${extension}`;
}

/**
 * Downscale an image File to fit within `maxPx` on its longest edge, preserving
 * aspect ratio, and re-encode it as WebP. Returns the original File untouched
 * only when the browser cannot decode it at all.
 *
 * Shared by ImageUpload (single) and GalleryUpload (multi) so the client-side
 * behaviour stays identical across both.
 *
 * **Why it re-encodes even an already-small image.** Uploads used to be served
 * through Cloudinary with `f_auto,q_auto`, which re-encoded on delivery: whatever
 * went up, a modern browser was sent WebP. An object store serves the bytes it
 * was given, so that job moves here — and a 900px PNG passed through untouched
 * would now genuinely be delivered as a multi-megabyte PNG. Re-encoding always
 * costs one canvas pass and makes the result predictable, which matters more now
 * that the stored object *is* the delivered object.
 *
 * **`toBlob` does not promise WebP.** Where the encoder is missing it silently
 * produces PNG instead, so the returned File carries whatever the blob actually
 * is and the caller signs *that* type — assuming WebP would mislabel the object
 * and the store would then serve a PNG announced as WebP.
 *
 * The PDF path does not come through here, and must not: a document is not a
 * photo, and there is nothing to downscale.
 */
export function resizeImage(file, maxPx = MAX_PX) {
  return new Promise((resolve) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      const scale = Math.min(1, maxPx / Math.max(img.width, img.height));
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(
        (blob) => {
          // A browser with no canvas encoding at all hands back null; the original
          // is still a real image, so upload it rather than failing the whole form.
          if (!blob) {
            resolve(file);
            return;
          }
          resolve(
            new File([blob], renamed(file.name, blob.type), {
              type: blob.type,
            })
          );
        },
        OUTPUT_TYPE,
        QUALITY
      );
    };
    // Anything the browser can't decode (a PDF picked by mistake, a corrupt file,
    // a HEIC no desktop browser reads) comes back untouched — the caller uploads
    // it as-is and the server's own type allowlist has the last word.
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(file);
    };
    img.src = url;
  });
}

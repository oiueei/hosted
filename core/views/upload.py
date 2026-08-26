"""
Upload views — hands the browser a short-lived ticket to write one object.

The client asks for a ticket, then PUTs the file straight to the bucket. Django
never handles the binary, which is the property this endpoint has always had and
keeps.

What changed with the move off Cloudinary is who enforces the rules. Before, the
server computed an HMAC over a set of upload parameters and the client echoed
them back; the storage provider then applied them. Now the rules are signed into
a presigned URL, and the storage provider refuses the upload — with
``SignatureDoesNotMatch`` — if a single one of them is altered in flight:

- the **key** is generated here (``secrets.token_urlsafe(16)``), so a client
  cannot name its own object and overwrite somebody else's;
- the **folder** is constrained to a known set, and forced in document mode, so
  an image can never be written into the documents folder (S4);
- the **content type** is picked from an allowlist and signed exactly. Raster
  photo types only — SVG is not among them, so an ``<img>``-rendered upload can
  never carry script — or ``application/pdf`` alone in document mode. Because it
  is signed rather than sniffed, the type the bucket later serves is the type
  decided here;
- the **size** is signed too, and this one is new. Cloudinary's own signature
  computation excluded ``max_file_size``, so signing it made ours diverge from
  theirs and every document upload failed with "Invalid Signature" — the S3
  outage. The cap then had to live in the browser (``PdfUpload``), where anyone
  could skip it. There is no such exclusion here: the client declares the length,
  this view refuses anything over the limit, and the exact number is signed.
"""

import secrets

from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.services import storage
from core.views._helpers import body_dict

# Image-mode folders only — "oiueei/documents" is document-mode-only (forced
# below, never client-chosen) and deliberately absent from this set. Both are
# derived from `storage.ASSET_FOLDERS` so this door and the fields that later
# accept the key back (`validators.validate_key_folder`) read one definition.
DOCUMENT_FOLDER = storage.DOCUMENT_FOLDER
IMAGE_FOLDERS = storage.ASSET_FOLDERS - {DOCUMENT_FOLDER}

# Raster photo types only. SVG and other script-bearing or non-photo formats are
# excluded so an <img>-rendered upload can never carry active content.
IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/heic",
    "image/heif",
    "image/avif",
    "image/bmp",
    "image/tiff",
}

# Document mode (the collection welcome doc): PDF and nothing else.
DOCUMENT_TYPES = {"application/pdf"}

# The welcome doc's long-standing 5 MB limit, now enforced where it cannot be
# skipped. Images are capped an order of magnitude above what they should ever
# be: the browser downscales to 1216px first, so a legitimate upload lands in the
# hundreds of kilobytes and this is a backstop against abuse, not a UX limit.
DOCUMENT_MAX_BYTES = 5 * 1024 * 1024
IMAGE_MAX_BYTES = 10 * 1024 * 1024


class UploadTicketView(APIView):
    """
    POST /api/v1/upload/ticket/

    Returns a one-object, short-lived upload ticket. The client sends the file as
    the raw body of a ``PUT`` to ``url`` with exactly the headers given, then
    stores ``key`` — the value that goes in the model field.

    Request body:
        {                                            # image (default)
            "folder": "oiueei/things",
            "content_type": "image/webp",
            "content_length": 183422
        }
        {                                            # PDF — folder is forced
            "kind": "document",
            "content_type": "application/pdf",
            "content_length": 812004
        }

    Response:
        {
            "url": "https://<bucket>.<endpoint>/<key>?X-Amz-...",
            "method": "PUT",
            "headers": {"x-amz-acl": ..., "Content-Type": ..., "Cache-Control": ...},
            "key": "oiueei/things/<random>",
            "public_url": "https://<media base>/oiueei/things/<random>"
        }

    ``public_url`` is where the object will be readable once the PUT succeeds, and
    it is answered here rather than derived by the client because the two can
    differ: the presigned URL always names the bucket, while reads go through
    whatever ``MEDIA_PUBLIC_BASE_URL`` points at — a CDN or a custom domain, on a
    deployment that has one. Stripping the query off ``url`` would quietly bypass
    it.
    """

    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key="user", rate="30/h", method="POST", block=True))
    def post(self, request):
        body = body_dict(request)
        # Anything that isn't the one document kind is an image upload — an unknown
        # value can only ever narrow to the (unchanged) image defaults.
        is_document = body.get("kind") == "document"

        if is_document:
            # Document mode always uses the documents folder — an image-mode
            # request may not choose it, keeping images out of it (S4).
            folder = DOCUMENT_FOLDER
            allowed_types, max_bytes = DOCUMENT_TYPES, DOCUMENT_MAX_BYTES
        else:
            folder = body.get("folder", "oiueei/users")
            # oiueei/documents isn't in IMAGE_FOLDERS, so naming it here falls
            # back like any other value the image mode doesn't recognise.
            if folder not in IMAGE_FOLDERS:
                folder = "oiueei/users"
            allowed_types, max_bytes = IMAGE_TYPES, IMAGE_MAX_BYTES

        content_type = body.get("content_type")
        if content_type not in allowed_types:
            raise ValidationError({"content_type": "Unsupported file type."})

        content_length = body.get("content_length")
        if not isinstance(content_length, int) or isinstance(content_length, bool):
            raise ValidationError({"content_length": "A byte count is required."})
        if not 1 <= content_length <= max_bytes:
            raise ValidationError({"content_length": f"Must be between 1 and {max_bytes} bytes."})

        # Random name within the folder. The key is the value stored on the model,
        # and its 128 bits of entropy are what keep a public object unguessable.
        key = f"{folder}/{secrets.token_urlsafe(16)}"
        ticket = storage.presign_upload(
            key, content_type=content_type, content_length=content_length, max_bytes=max_bytes
        )
        return Response({**ticket, "key": key, "public_url": storage.public_url(key)})

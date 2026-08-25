import { useState } from 'react';
import { FileInput, Button } from 'hds-react';
import { useTranslation } from 'react-i18next';
import { uploadImage, UploadTooLargeError } from '../utils/uploadImage';
import useTheeeme from '../hooks/useTheeeme';
import hdsLang from '../utils/hdsLang';

/**
 * Single-image upload component backed by a ticketed direct-to-bucket upload.
 * Images wider or taller than 1216 px are resized on the client before upload.
 * Shows a preview with a Remove button after upload or when an existing image
 * is present. Removing clears the field without deleting the stored object.
 *
 * Props:
 *   id          – HTML id for the FileInput
 *   label       – visible label text
 *   onChange    – called with the new public_id (or '') on upload / remove
 *   currentUrl  – full URL of the current saved image (for the initial preview)
 *   folder      – upload folder (default 'oiueei/users')
 *   helperText  – optional helper text shown below the input
 */
export default function ImageUpload({
  id,
  label,
  onChange,
  currentUrl,
  folder = 'oiueei/users',
  helperText,
}) {
  const { t, i18n } = useTranslation();
  const { uploadStyle } = useTheeeme();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [previewUrl, setPreviewUrl] = useState(currentUrl || null);

  // The preview is the saved image until this component uploads or removes one,
  // so it is local state that a *fresh* `currentUrl` has to win back — otherwise
  // a parent that reloads a different thing keeps showing the previous photo.
  //
  // Adjusted during render rather than from an effect: an effect renders the
  // stale preview, commits it, and only then corrects itself, which is the
  // cascade `react-hooks/set-state-in-effect` is about. Comparing against the
  // last value we synced is react.dev's own answer to "adjust state when a prop
  // changes" — React re-runs this component before touching the DOM, so nobody
  // sees the intermediate state.
  const [syncedUrl, setSyncedUrl] = useState(currentUrl);
  if (currentUrl !== syncedUrl) {
    setSyncedUrl(currentUrl);
    setPreviewUrl(currentUrl || null);
  }

  const handleRemove = () => {
    setPreviewUrl(null);
    onChange('');
  };

  const handleFiles = async (files) => {
    if (!files || files.length === 0) return;

    setFileInputKey((k) => k + 1); // reset immediately so HDS file list never shows
    setUploading(true);
    setError(null);

    try {
      const { publicId, url } = await uploadImage(files[0], folder);
      setPreviewUrl(url);
      onChange(publicId);
    } catch (err) {
      // The one failure worth naming: it is the user's file, and they can
      // do something about it. Everything else is ours to apologise for.
      setError(
        t(err instanceof UploadTooLargeError ? 'upload.imageTooLarge' : 'upload.uploadError')
      );
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="image-upload" style={uploadStyle}>
      {previewUrl && (
        <div className="image-upload-preview">
          <img src={previewUrl} alt={t('upload.previewAlt')} />
          <Button
            variant="supplementary"
            iconStart={<span aria-hidden="true">✕</span>}
            size="small"
            onClick={handleRemove}
            style={{ marginTop: 'var(--spacing-xs)' }}
          >
            {t('upload.remove')}
          </Button>
        </div>
      )}
      {!previewUrl && (
        <FileInput
          key={fileInputKey}
          id={id}
          label={label}
          accept="image/*"
          multiple={false}
          onChange={handleFiles}
          disabled={uploading}
          language={hdsLang(i18n.language)}
          buttonLabel={t('upload.addFile')}
          helperText={uploading ? t('upload.uploading') : helperText || t('upload.acceptHint')}
          errorText={error || undefined}
          invalid={!!error}
        />
      )}
    </div>
  );
}

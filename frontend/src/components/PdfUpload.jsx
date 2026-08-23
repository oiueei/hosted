import { useState } from 'react';
import { FileInput, Button } from 'hds-react';
import { useTranslation } from 'react-i18next';
import { uploadPdf, PDF_MAX_BYTES } from '../utils/uploadPdf';
import useTheeeme from '../hooks/useTheeeme';
import hdsLang from '../utils/hdsLang';

/**
 * Single-PDF upload backed by the same ticketed direct-to-bucket upload as
 * ImageUpload — no resize (a document is not a photo) and a 5 MB client-side cap.
 * Once a file is present it shows a link to it plus a Remove button; removing
 * clears the field without deleting the stored object.
 *
 * Props:
 *   id          – HTML id for the FileInput
 *   label       – visible label text
 *   onChange    – called with the new public_id (or '') on upload / remove
 *   currentUrl  – full URL of the current saved PDF (for the initial link)
 *   folder      – upload folder (default 'oiueei/documents')
 *   helperText  – optional helper text shown below the input
 */
export default function PdfUpload({
  id,
  label,
  onChange,
  currentUrl,
  folder = 'oiueei/documents',
  helperText,
}) {
  const { t, i18n } = useTranslation();
  const { uploadStyle } = useTheeeme();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [docUrl, setDocUrl] = useState(currentUrl || null);

  // Same shape as ImageUpload's preview, and same reason for adjusting it during
  // render instead of from an effect: the document shown is the saved one until
  // this component replaces or removes it, and a new `currentUrl` has to win.
  const [syncedUrl, setSyncedUrl] = useState(currentUrl);
  if (currentUrl !== syncedUrl) {
    setSyncedUrl(currentUrl);
    setDocUrl(currentUrl || null);
  }

  const handleRemove = () => {
    setDocUrl(null);
    onChange('');
  };

  const handleFiles = async (files) => {
    if (!files || files.length === 0) return;

    const file = files[0];
    setFileInputKey((k) => k + 1); // reset immediately so HDS file list never shows
    setError(null);

    if (file.size > PDF_MAX_BYTES) {
      setError(t('upload.pdfTooLarge'));
      return;
    }

    setUploading(true);
    try {
      const { publicId, url } = await uploadPdf(file, folder);
      setDocUrl(url);
      onChange(publicId);
    } catch {
      setError(t('upload.uploadError'));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="pdf-upload" style={uploadStyle}>
      {docUrl && (
        <div className="pdf-upload-current">
          <a href={docUrl} target="_blank" rel="noopener noreferrer">
            {t('upload.pdfView')}
          </a>
          <Button
            variant="supplementary"
            iconStart={<span aria-hidden="true">✕</span>}
            size="small"
            onClick={handleRemove}
          >
            {t('upload.remove')}
          </Button>
        </div>
      )}
      {!docUrl && (
        <FileInput
          key={fileInputKey}
          id={id}
          label={label}
          accept=".pdf,application/pdf"
          multiple={false}
          onChange={handleFiles}
          disabled={uploading}
          language={hdsLang(i18n.language)}
          buttonLabel={t('upload.addFileGeneric')}
          helperText={uploading ? t('upload.uploading') : helperText || t('upload.pdfHint')}
          errorText={error || undefined}
          invalid={!!error}
        />
      )}
    </div>
  );
}

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiFetch } from '../services/api';
import useTheeeme from '../hooks/useTheeeme';
import InlineConfirm from './InlineConfirm';

/**
 * The "report this listing" footer on ThingPage, shown to logged-in non-owners:
 * a secondary button like any other in the app — theeeme tokens, normal size, no
 * icon (it used to be a small supplementary one with an alert
 * icon, which read as neither a link nor a button). Clicking expands an
 * inline confirm right below the button (no modal, `aria-expanded`); confirming
 * POSTs the report. The owner is told *someone* reported it, never who — the
 * reporter stays server-side. Owns its own open/submitting state and reports
 * feedback via `onToast`.
 *
 * Props: `thingCode`, `onToast({type, message})`.
 */
export default function ThingReportFooter({ thingCode, onToast }) {
  const { t } = useTranslation();
  const { btnSecondaryStyle } = useTheeeme();
  const [open, setOpen] = useState(false);
  const [reporting, setReporting] = useState(false);

  const handleReport = async () => {
    setReporting(true);
    try {
      const res = await apiFetch(`/api/v1/things/${thingCode}/report/`, { method: 'POST' });
      setOpen(false);
      if (res.ok) {
        onToast({ type: 'success', message: t('thingPage.reportThanks') });
      } else if (res.status === 429) {
        onToast({ type: 'error', message: t('common.tooManyAttempts') });
      } else {
        onToast({ type: 'error', message: t('thingPage.reportError') });
      }
    } catch {
      setOpen(false);
      onToast({ type: 'error', message: t('common.connectionError') });
    } finally {
      setReporting(false);
    }
  };

  return (
    <div className="thing-report-footer">
      <InlineConfirm
        open={open}
        onTriggerClick={() => setOpen((o) => !o)}
        onClose={() => setOpen(false)}
        triggerLabel={t('thingPage.report')}
        triggerProps={{ variant: 'secondary', style: btnSecondaryStyle }}
        title={t('thingPage.reportConfirmTitle')}
        body={t('thingPage.reportConfirmBody')}
        confirmLabel={t('thingPage.reportConfirm')}
        onConfirm={handleReport}
        confirming={reporting}
        confirmProps={{ variant: 'danger', size: 'small', loadingText: t('thingPage.reporting') }}
      />
    </div>
  );
}

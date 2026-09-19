import { useTranslation } from 'react-i18next';
import { Button, Dialog } from 'hds-react';

/**
 * The confirm step before a confirmed reservation is cancelled — from either
 * side of it: the member in /my-bookings, a curator in /owner-bookings.
 *
 * A reservation auto-confirms, so cancelling one is not withdrawing a question:
 * it tells the other side, frees the slot for anybody else to take, and cannot
 * be undone. Both pages used to do it on a single press of a control sitting in
 * a dense table row — on the member's side an icon with a tooltip, on a phone
 * one mis-tap away from its neighbours (DESIGN checklist: irreversible actions
 * are signalled). Declining a pending request stays one click on purpose
 * (`OwnerBookingsPage.test.jsx`), and so does withdrawing your own request.
 *
 * The dialog names what is being cancelled — the thing, its date and time, and
 * on the curator's side whose reservation it is — so the confirm is a check, not
 * just a second press. Its way out is "Back", never "Cancel", which next to
 * "Cancel reservation" would read as the same action.
 *
 * Props: `row` (the page's table row: `_code`, `_thingHeadline`, `_when`),
 * `who` (optional line under the headline), `body`, `confirmLabel`, `busy`,
 * `onConfirm`, `onClose`, and the page's theeeme button styles.
 */
export default function CancelReservationDialog({
  row,
  who,
  body,
  confirmLabel,
  busy,
  onConfirm,
  onClose,
  btnStyle,
  btnSecondaryStyle,
}) {
  const { t } = useTranslation();
  return (
    <Dialog
      id="cancel-reservation-confirm"
      aria-labelledby="cancel-reservation-confirm-title"
      isOpen
      close={onClose}
      closeButtonLabelText={t('common.close')}
    >
      <Dialog.Header
        id="cancel-reservation-confirm-title"
        title={t('reservation.cancelConfirmTitle')}
      />
      <Dialog.Content>
        <p>{body}</p>
        <p style={{ marginBottom: 0 }}>
          <strong>{row._thingHeadline}</strong>
          {row._when && ` — ${row._when}`}
        </p>
        {who && <p style={{ margin: 'var(--spacing-2-xs) 0 0' }}>{who}</p>}
      </Dialog.Content>
      <Dialog.ActionButtons>
        <Button style={btnStyle} disabled={busy} onClick={onConfirm}>
          {confirmLabel}
        </Button>
        <Button variant="secondary" style={btnSecondaryStyle} onClick={onClose}>
          {t('common.back')}
        </Button>
      </Dialog.ActionButtons>
    </Dialog>
  );
}

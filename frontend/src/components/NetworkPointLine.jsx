import { useTranslation } from 'react-i18next';

/**
 * "Lent by {name} · {address} · {hours}": who lends a thing of a network and where
 * and when it is collected, from the pickup point the server resolved for its owner
 * (`thing.network_point`: `display_name` is the entity's name, else the
 * dinamizador's own, decided once on the server for every place that names it).
 * Nothing for a thing outside a network (`network_point` is null). The address and
 * hours are shown as written, never as links; React escapes them.
 */
export default function NetworkPointLine({ point, className = 'thing-card-info-row' }) {
  const { t } = useTranslation();
  if (!point) return null;
  const parts = [
    t('networkPoint.lentBy', { name: point.display_name || t('common.aMember') }),
    point.address,
    point.hours_note,
  ].filter(Boolean);
  return (
    <p className={className} data-testid="network-point-line">
      {parts.join(' · ')}
    </p>
  );
}

import { useLocalized } from '../utils/localized';
import { hasAmount } from '../constants/things';

/**
 * How deposits work, in the owner's words ("50 €, back when the drill comes home in
 * one piece"), under the deposit of a thing that has one. The server resolves whose
 * words they are (`thing.deposit_policy`: the pickup point's in a network, else the
 * collection's) and they may carry one text per language; it is plain text, never
 * markup. Nothing without a deposit: a policy with no amount to apply it to is noise.
 */
export default function DepositPolicy({ thing, className = 'text-muted' }) {
  const L = useLocalized();
  const text = thing?.deposit_policy ? L(thing.deposit_policy) : '';
  const hasDeposit = hasAmount(thing?.deposit);
  if (!hasDeposit || !text) return null;
  return (
    <p className={className} data-testid="deposit-policy">
      {text}
    </p>
  );
}

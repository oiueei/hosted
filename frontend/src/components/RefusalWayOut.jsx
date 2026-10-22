import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router';
import useTheeeme from '../hooks/useTheeeme';
import { loginPathFor } from '../utils/nextPath';
import ButtonLink from './ButtonLink';

/**
 * The way out of a "no permission" refusal, which is a dead end unless it says
 * where to go: with a session the way is Home (the groups they do belong to),
 * without one it is the sign-in, which brings them back to the page they were on.
 */
export default function RefusalWayOut() {
  const { t } = useTranslation();
  const location = useLocation();
  const { btnStyle, btnSecondaryStyle } = useTheeeme();

  return (
    <>
      <div className="spacer-m" />
      <div className="button-row-wide">
        {localStorage.getItem('userCode') ? (
          <ButtonLink to="/" style={btnSecondaryStyle}>
            {t('common.home')}
          </ButtonLink>
        ) : (
          <ButtonLink to={loginPathFor(location)} style={btnStyle}>
            {t('login.signIn')}
          </ButtonLink>
        )}
      </div>
    </>
  );
}

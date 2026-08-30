import { useEffect } from 'react';

import { useTranslation } from 'react-i18next';
import { Koros } from 'hds-react';
import useTheeeme from '../hooks/useTheeeme';
import ContactCorner from '../components/ContactCorner';
import ButtonLink from '../components/ButtonLink';

export default function NotFoundPage() {
  const { t } = useTranslation();
  useEffect(() => {
    document.title = t('titles.notFound');
  }, [t]);

  const { tc, btnStyle } = useTheeeme();
  const isLoggedIn = !!localStorage.getItem('userCode');

  return (
    <div
      className="form-page"
      style={tc.color_02 ? { backgroundColor: `var(--color-${tc.color_02})` } : undefined}
    >
      <div
        className="form-hero"
        style={
          tc.color_03
            ? {
                backgroundColor: `var(--color-${tc.color_03})`,
                '--hero-logo-color': `var(--color-${tc.color_02})`,
              }
            : undefined
        }
      >
        <div
          className="form-hero-content"
          style={tc.color_05 ? { '--hero-text-color': `var(--color-${tc.color_05})` } : undefined}
        >
          <ContactCorner />
          <h1 className="form-hero-title">{t('notFound.title')}</h1>
          <div>
            <ButtonLink to={isLoggedIn ? '/' : '/login'} style={btnStyle}>
              {isLoggedIn ? t('verify.goToHomepage') : t('verify.goToLogin')}
            </ButtonLink>
          </div>
        </div>
        <Koros
          className="form-hero-koros"
          type={localStorage.getItem('koro') || 'basic'}
          style={tc.color_02 ? { fill: `var(--color-${tc.color_02})` } : undefined}
        />
      </div>
      <div className="page-container">
        <p>{t('notFound.message')}</p>
      </div>
    </div>
  );
}

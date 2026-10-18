import { useTranslation } from 'react-i18next';
import useTheeeme from '../hooks/useTheeeme';
import PageLayout from '../components/PageLayout';
import ButtonLink from '../components/ButtonLink';
import useDocumentTitle from '../hooks/useDocumentTitle';

export default function NotFoundPage() {
  const { t } = useTranslation();
  useDocumentTitle(t('titles.notFound'));

  const { btnStyle } = useTheeeme();
  const isLoggedIn = !!localStorage.getItem('userCode');

  return (
    <PageLayout
      title={t('notFound.title')}
      heroActions={
        <ButtonLink to={isLoggedIn ? '/' : '/login'} style={btnStyle}>
          {isLoggedIn ? t('verify.goToHomepage') : t('verify.goToLogin')}
        </ButtonLink>
      }
    >
      <p>{t('notFound.message')}</p>
    </PageLayout>
  );
}

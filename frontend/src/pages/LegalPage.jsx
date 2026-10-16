import { useTranslation } from 'react-i18next';
import PageLayout from '../components/PageLayout';
import MarkdownText from '../components/MarkdownText';
import legalEs from '../legal/es';
import legalCa from '../legal/ca';
import legalEn from '../legal/en';
import useDocumentTitle from '../hooks/useDocumentTitle';

const CONTENT = { es: legalEs, ca: legalCa, en: legalEn };

/**
 * Public legal page (`/legal`): commitment (the manifesto, now public),
 * instance/operator identification, privacy, and basic terms — in the reader's
 * language. The content lives in `src/legal/{lang}.js` as Markdown so a
 * deployment can carry its own version: the standalone repo ships a generic
 * operator-neutral text, and a deployment can replace those files with its
 * own legal text.
 */
export default function LegalPage() {
  const { t, i18n } = useTranslation();
  useDocumentTitle(t('titles.legal'));
  const lang = (i18n.language || 'en').split('-')[0];
  const content = CONTENT[lang] || CONTENT.en;
  const isLoggedIn = !!localStorage.getItem('userCode');

  return (
    <PageLayout
      title={t('legal.pageTitle')}
      backTo={isLoggedIn ? '/' : '/login'}
      backLabel={isLoggedIn ? t('common.home') : t('verify.goToLogin')}
    >
      <div className="legal-content" style={{ maxWidth: '720px' }}>
        <MarkdownText text={content} headingBase={2} />
      </div>
    </PageLayout>
  );
}

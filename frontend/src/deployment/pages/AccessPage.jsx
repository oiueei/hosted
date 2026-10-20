import { useEffect, useRef } from 'react';
import { Link as HdsLink } from 'hds-react';
import { useParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import PageLayout from '../../components/PageLayout';
import useDocumentTitle from '../../hooks/useDocumentTitle';
import useTheeeme from '../../hooks/useTheeeme';
import { apiFetch } from '../../services/api';

// What needs asking for, in the order the page tells it: a library (lending and renting
// out are one permission here) and a shed. A community is asked for from the collection
// form's own option. The same two words the server counts by
// (`hosted.models.AccessInterest`) and the emails and `/new` link to (`/access/<need>`).
const NEEDS = ['library', 'shed'];

/**
 * `/access/:need` — what opens on request, one section per need.
 *
 * The emails send a person here for the one thing they would need to ask for, and the
 * page explains both, always: somebody who came for the library may well want the
 * shed too. When the address names one, the page goes to it, puts the focus on its
 * heading and reports — once, as a bare number and nothing about the reader — that the
 * section was opened. Each section has a "Request access" button of its own that goes
 * to the form with `?for=<need>&lang=<the language on screen>`, so the count of presses can be told apart by need and the form comes in the reader's language.
 *
 * It belongs to this deployment: what is asked first, and where, is one operator's.
 */
export default function AccessPage() {
  const { need } = useParams();
  const { t, i18n } = useTranslation();
  const { btnStyle } = useTheeeme();
  const reported = useRef(false);
  const requested = NEEDS.includes(need) ? need : null;
  // The form is opened in the language on screen, which is not always the browser's.
  const language = i18n.resolvedLanguage || i18n.language;

  useDocumentTitle(t('access.docTitle'));

  useEffect(() => {
    // A ref, not state: StrictMode runs the effect twice on mount and a second run
    // must not count the same opening again.
    if (!requested || reported.current) return;
    reported.current = true;
    const heading = document.getElementById(requested);
    heading?.scrollIntoView?.();
    heading?.focus();
    apiFetch('/api/v1/access/seen/', {
      method: 'POST',
      body: JSON.stringify({ need: requested }),
    }).catch(() => {
      // A count that fails is nobody's problem: the page says nothing about it.
    });
  }, [requested]);

  const isLoggedIn = !!localStorage.getItem('userCode');
  const button = t('access.button');

  return (
    <PageLayout
      title={t('access.title')}
      description={t('access.intro')}
      backTo={isLoggedIn ? '/' : '/login'}
      backLabel={isLoggedIn ? t('common.home') : t('verify.goToLogin')}
    >
      <div className="legal-content" style={{ maxWidth: '720px' }}>
        {NEEDS.map((name) => (
          <section key={name}>
            <h2 id={name} tabIndex={-1}>
              {t(`access.${name}.title`)}
            </h2>
            <p>{t(`access.${name}.body`)}</p>
            <div className="button-row-wide">
              <HdsLink
                href={`/request-access/?for=${name}&lang=${language}`}
                useButtonStyles
                style={btnStyle}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`${button}. ${t('common.opensInNewTab')}`}
              >
                {button}
              </HdsLink>
            </div>
            <p style={{ color: 'var(--color-black-60, #666)' }}>{t('access.formNote')}</p>
          </section>
        ))}
      </div>
    </PageLayout>
  );
}

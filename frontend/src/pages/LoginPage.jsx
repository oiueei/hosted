import { useEffect, useState } from 'react';
import { useTranslation, Trans } from 'react-i18next';
import { Link } from 'react-router';
import { TextInput, Button, Notification, Koros } from 'hds-react';
import { getCsrfToken } from '../services/api';
import useTheeeme from '../hooks/useTheeeme';
import ContactCorner from '../components/ContactCorner';
import { popInPath, faqPath } from '../deployment';
import ButtonLink from '../components/ButtonLink';

export default function LoginPage() {
  const { t } = useTranslation();
  useEffect(() => {
    document.title = t('titles.login');
  }, [t]);
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState(null); // 'success' | 'alert' | 'error'
  const [message, setMessage] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus(null);
    setLoading(true);
    try {
      const res = await fetch('/api/v1/auth/request-link/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify({ email }),
      });
      if (res.ok) {
        setStatus('success');
        setMessage(t('login.magicLinkSent'));
      } else if (res.status === 429) {
        setStatus('error');
        setMessage(t('common.tooManyAttempts'));
      } else {
        setStatus('error');
        setMessage(t('login.errorSendingLink'));
      }
    } catch {
      setStatus('error');
      setMessage(t('common.connectionError'));
    } finally {
      setLoading(false);
    }
  };

  const { tc, btnStyle, btnSecondaryStyle } = useTheeeme();

  return (
    <div
      className="form-page"
      style={tc.color_02 ? { backgroundColor: `var(--color-${tc.color_02})` } : undefined}
    >
      <div
        className="form-hero"
        style={tc.color_03 ? { backgroundColor: `var(--color-${tc.color_03})` } : undefined}
      >
        <div
          className="form-hero-content"
          style={tc.color_05 ? { '--hero-text-color': `var(--color-${tc.color_05})` } : undefined}
        >
          <ContactCorner />
          <h1 className="form-hero-title" aria-label={t('login.title')}>
            <span className="form-hero-title-logo" aria-hidden="true" />
          </h1>
        </div>
        <Koros
          className="form-hero-koros"
          type={localStorage.getItem('koro') || 'basic'}
          style={tc.color_02 ? { fill: `var(--color-${tc.color_02})` } : undefined}
        />
      </div>
      <div className="page-container">
        {/* What this page is, as a heading rather than a bold paragraph — the
            hero's own <h1> is the logo, so this is the first thing with words
            in it. Level 2 keeps the outline whole (h1 → h2); how big it looks
            (Body XL bold) lives in .login-pitch. */}
        <h2 className="login-pitch measure">{t('login.pitch')}</h2>
        {status ? (
          <>
            <Notification
              autofocus
              label={
                status === 'success'
                  ? t('common.sent')
                  : status === 'alert'
                    ? t('common.warning')
                    : t('common.error')
              }
              type={status}
            >
              {message}
            </Notification>
            <div style={{ marginTop: 'var(--spacing-s)' }}>
              <Button
                variant="secondary"
                onClick={() => {
                  setStatus(null);
                  setMessage('');
                }}
              >
                {t('login.tryAnotherEmail')}
              </Button>
            </div>
          </>
        ) : (
          <form
            onSubmit={handleSubmit}
            className="measure"
            style={{ marginTop: 'var(--spacing-s)' }}
          >
            <TextInput
              id="login-email"
              label={t('login.emailLabel')}
              type="email"
              placeholder={t('login.emailPlaceholder')}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="section-mt"
            />
            <div>
              <Button type="submit" fullWidth disabled={loading} style={btnStyle}>
                {loading ? t('common.sending') : t('login.signIn')}
              </Button>
            </div>
          </form>
        )}
        {/* Only when this deployment has an open door (frontend/src/deployment).
            Without one there is nowhere for the button to go, and offering it
            would send a stranger to a 404 instead of telling them the truth:
            you get in here by invitation. */}
        {popInPath && (
          <div className="measure" style={{ marginTop: 'var(--spacing-s)' }}>
            <ButtonLink to={popInPath} fullWidth style={btnSecondaryStyle}>
              {t('login.popIn')}
            </ButtonLink>
          </div>
        )}
        {/* The one expectation this screen owes a newcomer, in brick and at a
            size that is read rather than skimmed past — directly under the
            door, so nobody signs in without having met it. Same sentence, word
            for word, as the FAQ and the legal notice (common.alphaNotice). */}
        <p className="login-alpha measure">{t('common.alphaNotice')}</p>
        {/* Only when this deployment has a help page (frontend/src/deployment).
            Upstream there is no FAQ content to link to — same reasoning as
            aboutPath: a link to a 404 is worse than one link fewer. */}
        {faqPath && (
          <p className="measure" style={{ marginTop: 'var(--spacing-2-xs)' }}>
            <Link to={faqPath} style={{ textDecoration: 'underline' }}>
              {t('login.faqLink')}
            </Link>
          </p>
        )}
        {/* Everything a newcomer may want to read BEFORE typing an email, below
            the door rather than in front of it: whoever already has an account
            sees only the title and the form. The claims themselves are
            unchanged — what moved is when you meet them. One block, one text
            size (.login-footnotes), so a checkable claim never reads as small
            print next to the licence. */}
        <div className="login-footnotes">
          <p className="measure">
            <Trans
              i18nKey="login.licence"
              components={[
                <span key="0" />,
                // eslint-disable-next-line jsx-a11y/anchor-has-content -- the link text is injected by <Trans> from the i18n string at runtime
                <a
                  key="1"
                  href="https://github.com/oiueei/standalone"
                  target="_blank"
                  rel="noopener noreferrer"
                />,
              ]}
            />
          </p>
          <p
            className="measure"
            style={{ marginTop: 'var(--spacing-s)', color: 'var(--color-black-60)' }}
          >
            <Trans
              i18nKey="login.noBanner"
              components={[
                <span key="0" />,
                // eslint-disable-next-line jsx-a11y/anchor-has-content -- the link text is injected by <Trans> from the i18n string at runtime
                <a
                  key="1"
                  href="https://github.com/oiueei/standalone#privacy"
                  target="_blank"
                  rel="noopener noreferrer"
                />,
              ]}
            />
          </p>
          {/* Per-deployment note (who operates this instance and where it runs): empty in
              the standalone repo, filled on the deploy branch — the same split as
              src/legal/. Only rendered when the operator has actually written one. */}
          {t('login.operator') ? (
            <p
              className="measure"
              style={{ marginTop: 'var(--spacing-2-xs)', color: 'var(--color-black-60)' }}
            >
              {t('login.operator')}
            </p>
          ) : null}
          {/* The locked-out user's lifeline, paired with the legal link at the
              foot of the page: both are things you go looking for deliberately,
              and neither belongs between someone and the field they came for. */}
          <p className="measure" style={{ marginTop: 'var(--spacing-m)' }}>
            <Link to="/contact" style={{ textDecoration: 'underline' }}>
              {t('login.loginHelp')}
            </Link>
          </p>
          <p className="measure" style={{ marginTop: 'var(--spacing-2-xs)' }}>
            <Link to="/legal" className="legal-link">
              {t('login.legalLink')}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

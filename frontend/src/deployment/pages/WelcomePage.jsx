import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { useTranslation, Trans } from 'react-i18next';
import { Koros } from 'hds-react';
import BackLink from '../../components/BackLink';
import FeedbackLink from '../../components/FeedbackLink';
import { apiFetch } from '../../services/api';
import useTheeeme from '../../hooks/useTheeeme';
import ContactCorner from '../../components/ContactCorner';
import ButtonLink from '../../components/ButtonLink';

// Every persona owns a demo collection since the 2026-08 seed round gave Lele and
// Lulu one each — before that the two of them carried no link, and the comment
// here said so. The render filters by accessibleCodes, so a persona whose group
// the visitor cannot reach simply shows no link row: the two COMMUNITY groups are
// PRIVATE, and a non-member sees the story without the link.
const PERSONA_LINKS = {
  Lala: [{ code: 'La1aC1', key: 'personaLalaLink2' }],
  Lele: [{ code: 'L3L3C1', key: 'personaLeleLink1' }],
  Lili: [{ code: 'l1l1C1', key: 'personaLiliLink1' }],
  Lolo: [{ code: 'l0l0C1', key: 'personaLoloLink1' }],
  Lulu: [{ code: '1u1uC1', key: 'personaLuluLink1' }],
};

// The seeded demo collections these personas actually live in. The intro copy
// has to switch on *these* being reachable, not on the visitor having any
// collection at all: an ordinary invited member — the main membership model —
// has a non-empty accessible set made entirely of real groups, and used to be
// promised "we've shared a few example collections with you" above five stories
// with no links under them.
const DEMO_CODES = Object.values(PERSONA_LINKS).flatMap((links) => links.map(({ code }) => code));

export default function WelcomePage() {
  const { t } = useTranslation();
  useEffect(() => {
    document.title = t('titles.welcome');
    localStorage.setItem('seenWelcome', 'true');
  }, [t]);
  const [userName, setUserName] = useState('');
  const [accessibleCodes, setAccessibleCodes] = useState(() => new Set());
  // Read once on mount, like every other page in the app. It decides which doors
  // this page offers: a member gets "create a collection" / "edit profile", a
  // stranger gets whichever door this deployment opens for them (popInPath,
  // null upstream — then /login, the one that always exists). Every
  // action below used to point at a RequireAuth route, so a visitor who finally
  // reached this page still hit a login form on whatever they clicked.
  const [isAuthenticated] = useState(() => !!localStorage.getItem('userCode'));

  // Both calls are `optionalAuth` because this is a PUBLIC route: it is the page
  // that explains what OIUEEI is, so a stranger handed the link must be able to
  // read it. Without the flag a plain `apiFetch` 401 hard-navigates to /login
  // from inside the helper — the `.catch()` below never gets a say — and the one
  // page written for people without an account was the one they couldn't reach.
  // Signed in, both resolve and add the greeting and the example-collection links.
  useEffect(() => {
    apiFetch('/api/v1/auth/me/', { optionalAuth: true })
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((data) => setUserName(data.name || data.email || ''))
      .catch(() => {});
  }, []);

  useEffect(() => {
    apiFetch('/api/v1/invited-collections/', { optionalAuth: true })
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((data) => setAccessibleCodes(new Set((data || []).map((c) => c.code))))
      .catch(() => {});
  }, []);
  const { tc, koro, btnStyle, btnSecondaryStyle } = useTheeeme();

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
          {isAuthenticated && <BackLink to="/" label={t('common.home')} />}
          <div className="spacer-m" />
          {userName && (
            <p
              style={{
                fontSize: 'var(--fontsize-heading-m)',
                fontWeight: 700,
                lineHeight: 'var(--lineheight-m)',
                letterSpacing: '-0.2px',
                color: 'var(--hero-text-color, var(--color-black-90))',
              }}
            >
              {t('welcome.greeting', { name: userName })}
            </p>
          )}
          <h1 className="form-hero-title">{t('welcome.pageTitle')}</h1>
          <div className="button-row-wide" style={{ paddingBottom: 'var(--spacing-s)' }}>
            {isAuthenticated ? (
              <>
                <ButtonLink
                  to="/collections/new"
                  state={{
                    backPath: '/welcome',
                    backLabel: t('welcome.pageTitle'),
                  }}
                  style={btnStyle}
                >
                  {t('welcome.createCollection')}
                </ButtonLink>
                <ButtonLink
                  to="/me/edit"
                  state={{
                    backPath: '/welcome',
                    backLabel: t('welcome.pageTitle'),
                  }}
                  style={btnSecondaryStyle}
                >
                  {t('welcome.editProfile')}
                </ButtonLink>
              </>
            ) : (
              <>
                <ButtonLink to="/popin" style={btnStyle}>
                  {t('login.popIn')}
                </ButtonLink>
                <ButtonLink to="/login" style={btnSecondaryStyle}>
                  {t('login.signIn')}
                </ButtonLink>
              </>
            )}
          </div>
        </div>
        <Koros
          className="form-hero-koros"
          type={koro}
          style={tc.color_02 ? { fill: `var(--color-${tc.color_02})` } : undefined}
        />
      </div>
      <div className="page-container welcome-content">
        <p
          style={{
            fontSize: 'var(--fontsize-body-xl)',
            fontWeight: 700,
            lineHeight: '32px',
          }}
        >
          {t('welcome.description')}
        </p>
        <div className="spacer-m" />
        <p>{t('welcome.createShare')}</p>
        <div className="spacer-xl" />
        <h2>{t('welcome.commitmentTitle')}</h2>
        <div className="spacer-s" />
        <p>{t('welcome.commitmentBody1')}</p>
        <div className="spacer-s" />
        <p>
          <Trans
            i18nKey="welcome.commitmentBody2"
            components={[
              <span key="0" />,
              // eslint-disable-next-line jsx-a11y/anchor-has-content -- the link text is injected by <Trans> from the i18n string at runtime
              <a
                key="1"
                href="https://github.com/oiueei/standalone/blob/main/DESIGN.md#9-user-data-is-never-a-product"
                target="_blank"
                rel="noopener noreferrer"
              />,
            ]}
          />
        </p>
        <div className="spacer-s" />
        <p>
          <Link to="/legal" style={{ textDecoration: 'underline' }}>
            {t('welcome.legalLink')}
          </Link>
        </p>
        {/* Beside the legal link rather than at the foot of the page: this is
            the moment somebody is already inside and has real questions, and
            the two links answer the same impulse at different depths. */}
        <p>
          <Link to="/faq" style={{ textDecoration: 'underline' }}>
            {t('welcome.faqLink')}
          </Link>
        </p>
        <div className="spacer-xl" />
        <h2>{t('welcome.whoUsesTitle')}</h2>
        <div className="spacer-s" />
        <p>
          {DEMO_CODES.some((code) => accessibleCodes.has(code))
            ? t('welcome.exampleIntro')
            : t('welcome.exampleIntroEmpty')}
        </p>
        <div className="spacer-s" />
        {['Lala', 'Lele', 'Lili', 'Lolo', 'Lulu'].map((name, i) => (
          <div key={name}>
            {i > 0 && <div className="spacer-l" />}
            <p>
              <b>{t(`welcome.persona${name}Title`)}</b> {t(`welcome.persona${name}Body`)}
            </p>
            {(() => {
              const links = PERSONA_LINKS[name].filter(({ code }) => accessibleCodes.has(code));
              if (links.length === 0) return null;
              return (
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 'var(--spacing-xs)',
                    marginTop: 'var(--spacing-xs)',
                  }}
                >
                  {links.map(({ code, key }) => (
                    <Link
                      key={code}
                      to={`/collections/${code}`}
                      style={{
                        color: tc.color_01 ? `var(--color-${tc.color_01})` : 'var(--color-bus)',
                        textDecoration: 'underline',
                        fontSize: 'var(--fontsize-body-l)',
                        fontWeight: 700,
                      }}
                    >
                      {t(`welcome.${key}`)} →
                    </Link>
                  ))}
                </div>
              );
            })()}
          </div>
        ))}
        <div className="spacer-xl" />
        <div className="button-row-wide">
          {/* Signed in: straight home. Signed out: the deployment's open door
              if it has one, else /login — the door it does have. */}
          <ButtonLink to={isAuthenticated ? '/' : '/popin'} style={btnStyle}>
            {isAuthenticated ? t('welcome.enterCta') : t('login.popIn')}
          </ButtonLink>
        </div>
        <FeedbackLink />
      </div>
    </div>
  );
}

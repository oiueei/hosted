import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router';
import { useTranslation } from 'react-i18next';
import PageLayout from '../../components/PageLayout';
import MarkdownText from '../../components/MarkdownText';
import { loadFaqEntries } from '../faq';

/**
 * The help page (`/faq`) — what this service costs, who runs it, what state it
 * is in, and how the everyday things work.
 *
 * It belongs to this deployment rather than to the product, which is why it
 * lives here: half the answers are one operator's commitments, and a
 * self-hoster copying them would be publishing claims that are not theirs.
 *
 * Built like `LegalPage` — same chrome, same `MarkdownText`, same reading width
 * — with one deliberate difference: the content is an array, so every question
 * gets its own `<h2 id>` and `/faq#precio` lands on the answer. A flat list and
 * not an accordion, so Ctrl+F finds the text and there is no state to get wrong.
 */
export default function FaqPage() {
  const { t, i18n } = useTranslation();
  const { hash } = useLocation();
  const [entries, setEntries] = useState([]);
  const lang = (i18n.language || 'en').split('-')[0];

  useEffect(() => {
    document.title = t('titles.faqPage');
  }, [t]);

  useEffect(() => {
    let cancelled = false;
    loadFaqEntries(lang).then((loaded) => {
      if (!cancelled) setEntries(loaded);
    });
    return () => {
      cancelled = true;
    };
  }, [lang]);

  // The browser cannot honour `/faq#precio` on its own here: the route is lazy
  // and the answers arrive a tick after that, so when the hash is read the
  // element it names does not exist yet. Anchors that only work on a reload are
  // worse than no anchors — the whole point is pasting one into a chat.
  useEffect(() => {
    if (!hash || entries.length === 0) return;
    document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView();
  }, [hash, entries]);

  const isLoggedIn = !!localStorage.getItem('userCode');

  return (
    <PageLayout
      title={t('faqPage.pageTitle')}
      backTo={isLoggedIn ? '/' : '/login'}
      backLabel={isLoggedIn ? t('common.home') : t('verify.goToLogin')}
    >
      <div className="legal-content" style={{ maxWidth: '720px' }}>
        {entries.map(({ id, q, a, link }) => (
          <section key={id}>
            <h2 id={id}>{q}</h2>
            <MarkdownText text={a} headingBase={2} />
            {/* Rendered here and not as a Markdown link on purpose:
                `MarkdownText` gives every anchor target="_blank", which is right
                for an outside link and wrong for /legal. That component is
                shared with upstream, so this deployment does not get to change it. */}
            {link && (
              <p>
                <Link to={link.to}>{link.label} →</Link>
              </p>
            )}
          </section>
        ))}
      </div>
    </PageLayout>
  );
}

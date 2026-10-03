import { useEffect, useRef, useState, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Button, Koros, Notification, Tag, TextArea } from 'hds-react';
import { apiFetch } from '../services/api';
import AccountMenu from '../components/AccountMenu';
import BackLink from '../components/BackLink';
import PageLayout from '../components/PageLayout';
import LoadingSpinner from '../components/LoadingSpinner';
import MarkdownText, { sanitizeUrl } from '../components/MarkdownText';
import ShareCollectionMenu from '../components/ShareCollectionMenu';
import ThingLinkbox from '../components/ThingLinkbox';
import InboxNotifications from '../components/InboxNotifications';
import DemoNotice from '../components/DemoNotice';
import HeroPhoto from '../components/HeroPhoto';
import useTheeeme from '../hooks/useTheeeme';
import ContactCorner from '../components/ContactCorner';
import RecommendGuest from '../components/RecommendGuest';
import { useLocalized } from '../utils/localized';
import ButtonLink from '../components/ButtonLink';
import StatusRegion from '../components/StatusRegion';
import CollectionMenu, { CollectionDownloadsStatus } from '../components/CollectionMenu';
import useCollectionDownloads from '../hooks/useCollectionDownloads';
import useCollectionLanguage from '../hooks/useCollectionLanguage';
import { DATE_TYPES } from '../constants/things';

/**
 * Cards mounted before the "Show more" button appears.
 *
 * The collection serialises **every** thing it holds and there is no ceiling on
 * how many that is (`COLLECTION_THINGS_BLOCK` is off by default), so a lending
 * library with 200 items used to mount 200 `ThingLinkbox`es — each with its own
 * theeeme, localisation and booking view-model — on first paint. The photos were
 * already `loading="lazy"`, so what this cuts is the mount cost, which is what
 * a mid-range Android actually feels (DESIGN §7).
 *
 * Deliberately a **render** cap, not server pagination: the tag chips count
 * across the whole collection, and a paginated payload would make those counts
 * lie. 24 fills the widest grid (4 columns) six rows deep.
 */
const CARDS_PER_PAGE = 24;

// What the member's "Invite someone" button controls (aria-controls) and the
// form it opens sits under.
const RECOMMEND_BOX_ID = 'recommend-box';

export default function CollectionPage() {
  const { code } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { tc, koro, btnStyle, btnSecondaryStyle } = useTheeeme();
  const [collection, setCollection] = useState(null);
  const [error, setError] = useState('');
  const [broadcastOpen, setBroadcastOpen] = useState(false);
  const [broadcastMessage, setBroadcastMessage] = useState('');
  const [broadcastSending, setBroadcastSending] = useState(false);
  const [broadcastResult, setBroadcastResult] = useState(null);
  const [activeTag, setActiveTag] = useState(null);
  const [shownCount, setShownCount] = useState(CARDS_PER_PAGE);
  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState(false);
  const [recommendOpen, setRecommendOpen] = useState(false);
  const recommendButtonRef = useRef(null);
  // The owner may have written the collection's text once per language; every
  // child (cards, share menu, back labels) gets the resolved words from here.
  const L = useLocalized();
  const headline = L(collection?.headline);
  useCollectionLanguage(collection?.language, [collection?.headline, collection?.description]);
  // Called unconditionally (it is a hook): non-curators simply never see the
  // menu that offers it. One call owns the calendar, stats and JSON
  // downloads, and the page hands it to the menu and to the status zone.
  const downloads = useCollectionDownloads(code);
  useEffect(() => {
    document.title = collection
      ? t('titles.collection', { headline })
      : t('titles.collectionDefault');
  }, [collection, headline, t]);

  // Stable across renders (functional setState, no deps) so memoised ThingLinkbox
  // cards don't re-render when unrelated page state (broadcast box, tag filter)
  // changes. Shared by the active and inactive thing lists.
  const handleUpdateThing = useCallback((thingCode, updates) => {
    setCollection((prev) => ({
      ...prev,
      things: prev.things.map((thg) => (thg.code === thingCode ? { ...thg, ...updates } : thg)),
    }));
  }, []);

  useEffect(() => {
    // Guard against a fast A→B navigation: without aborting, collection A's
    // response can land after B's and render the wrong collection. Aborting on
    // cleanup (code change / unmount) drops the stale fetch. Mirrors ThingPage.
    const controller = new AbortController();
    const { signal } = controller;
    const fetchCollection = async () => {
      try {
        const res = await apiFetch(`/api/v1/collections/${code}/`, { signal });
        if (signal.aborted) return;
        if (res.ok) {
          const data = await res.json();
          if (signal.aborted) return;
          setCollection(data);
        } else if (res.status === 403) {
          setError('collectionPage.noPermission');
        } else if (res.status === 404) {
          setError('collectionPage.notFound');
        } else {
          setError('collectionPage.errorLoading');
        }
      } catch {
        if (!signal.aborted) setError('common.connectionError');
      }
    };
    fetchCollection();
    return () => controller.abort();
    // `error` holds the i18n *key*, translated where it is painted, so this effect
    // never reads `t`: `useCollectionLanguage` changes the language once the first
    // response lands, `t` gets a new identity, and listing it here fetched the
    // whole collection a second time.
  }, [code, navigate]);

  if (error) {
    return (
      <PageLayout title={t('common.error')} backTo="/" backLabel={t('common.home')}>
        <Notification label={t('common.error')} type="error">
          {t(error)}
        </Notification>
      </PageLayout>
    );
  }

  if (!collection) {
    return <LoadingSpinner />;
  }

  const handleBroadcast = async () => {
    setBroadcastSending(true);
    setBroadcastResult(null);
    try {
      const res = await apiFetch(`/api/v1/collections/${code}/broadcast/`, {
        method: 'POST',
        body: JSON.stringify({ message: broadcastMessage }),
      });
      const data = await res.json();
      if (res.ok) {
        setBroadcastResult({
          type: 'success',
          message: t('broadcast.sent', { count: data.recipients }),
        });
        setBroadcastMessage('');
      } else {
        // `detail` first, then `error`, the same order `extractApiError` reads
        // them in: this view answers `{error}` on its own refusals, but the one
        // an owner actually meets is the daily cap (5/day), and that arrives
        // from the rate-limit handler as `{detail}`. Reading only `error` turned
        // "slow down and try again later" into a bare "Error" — no reason, no
        // hint that tomorrow works, on the one screen where the owner is left
        // wondering whether the group got the message.
        setBroadcastResult({
          type: 'error',
          message: data.detail || data.error || t('common.error'),
        });
      }
    } catch {
      setBroadcastResult({ type: 'error', message: t('common.connectionError') });
    }
    setBroadcastSending(false);
  };

  // Join a PUBLIC group you are only browsing. The signed-in half of
  // login-to-act: an anonymous reader gets `/collections/:code/join`, which
  // takes an email and mails a magic link — no use at all to a session that
  // already exists, so the reader with the most intent had no way in. Re-fetches
  // rather than patching `is_member` locally: joining changes several fields at
  // once (the member roster, the digest switch, what the cards may offer), and
  // the server is the only thing that knows all of them.
  const handleJoin = async () => {
    setJoining(true);
    setJoinError(false);
    try {
      const res = await apiFetch(`/api/v1/collections/${code}/join/`, { method: 'POST' });
      if (res.ok) {
        const fresh = await apiFetch(`/api/v1/collections/${code}/`);
        if (fresh.ok) setCollection(await fresh.json());
        else setJoinError(true);
      } else {
        setJoinError(true);
      }
    } catch {
      setJoinError(true);
    }
    setJoining(false);
  };

  const userCode = localStorage.getItem('userCode');
  // The strict founder check — still what the attribution line and the
  // INACTIVE/delete-adjacent controls key on. Everything else that used to
  // read `isOwner` for an admin power now reads `isCurator` instead, the
  // server-computed field that also admits a co-owner.
  const isOwner = userCode === collection.owner;
  const isCurator = !!collection.is_curator;
  // The team the hero names, founder first. The API sends a co-curator's bare
  // `name` — never an email standing in for it (L2) — so one who set none is
  // counted at the end instead of listed: comma-joined, an empty name left
  // "Oriol, ," on the page.
  const team = [
    { code: collection.owner, name: collection.owner_name },
    ...(collection.co_owners ?? []),
  ];
  const namedTeam = team.filter((member) => member.name);
  const unnamedTeamCount = team.length - namedTeam.length;
  const isAuthenticated = !!userCode;
  // The Community/visibility tags in the H1 are purely informational — no
  // click, no delete, so no hover/focus state to design for — so they follow
  // the theeeme's primary-button colours (color_01/color_06) instead of a
  // fixed HDS token pair, matching every other themed surface on the page.
  // They are also the curators' own bookkeeping — how the group is set up, not
  // something a member or a passer-by needs before the title (CA, 2026-09-21) —
  // so both render for `isCurator` only.
  const tagTheme = tc.color_01
    ? {
        '--tag-background': `var(--color-${tc.color_01})`,
        '--tag-color': `var(--color-${tc.color_06})`,
      }
    : undefined;

  // Active (non-inactive) things, optionally narrowed to the selected tag chip.
  const visibleThings = collection.things.filter((thg) => thg.status !== 'INACTIVE');
  const collectionTags = collection.tags || [];
  const effectiveTag = activeTag && collectionTags.includes(activeTag) ? activeTag : null;
  const matchingThings = effectiveTag
    ? visibleThings.filter((thg) => (thg.tags || []).includes(effectiveTag))
    : visibleThings;
  // Newest first, then capped at what's actually been asked for. Sorting before
  // the slice is what makes "Show more" append older things rather than reshuffle.
  const sortedThings = [...matchingThings].sort(
    (a, b) => new Date(b.created) - new Date(a.created)
  );
  const shownThings = sortedThings.slice(0, shownCount);
  const remainingThings = sortedThings.length - shownThings.length;
  // Who may put a thing here: a curator, or a member of a COMMUNITY group —
  // the same rule `Collection.can_add_thing` enforces. Mode alone is not enough:
  // a reader who is not a member (signed in or not) would be sent through the
  // whole form, photos uploaded and all, to collect a 403 at the end.
  const canAddThing = isCurator || (collection.mode === 'COMMUNITY' && !!collection.is_member);
  // Who may hand the group's link to someone: a curator, and — in a PUBLIC group
  // — any member (CA, 2026-09-29). A PUBLIC group is shared by its own address,
  // with no token to mint, rotate or revoke, so a member can pass it on without
  // holding anything a curator would need to pull back; it is the cheapest way to
  // bring new people in, and nothing had ever asked a member to. In a PRIVATE one
  // the link is the curators' credential, and the member has "Recommend" instead.
  const canShare = isCurator || (collection.visibility === 'PUBLIC' && !!collection.is_member);
  // A signed-out reader of a PUBLIC group has no card to click in two places: an
  // empty group, and the bottom of a COMMUNITY one, where to *contribute* they
  // would have to press "Request" on somebody else's thing. CA reopened the
  // hero's removed join line for exactly these two cases (2026-09-29) — but in
  // the content, not the hero, and only where there is no button to press. A
  // PROPRIETARY group with things needs nothing: its door is each thing's button.
  // Which line: a COMMUNITY group asks for what the reader could add; a
  // PROPRIETARY one that is empty promises the one thing a member does get — the
  // summary of what arrives — but only when the group sends one. With its digest
  // set to "None" nobody hears anything, so the line just says "Join the group".
  const sendsDigest = !!collection.digest_frequency && collection.digest_frequency !== 'NONE';
  const anonJoinKey =
    !isAuthenticated && collection.visibility === 'PUBLIC'
      ? collection.mode === 'COMMUNITY'
        ? 'collectionPage.anonJoinCommunity'
        : visibleThings.length === 0
          ? sendsDigest
            ? 'collectionPage.anonJoinEmpty'
            : 'collectionPage.anonJoinPlain'
          : null
      : null;
  // A collection locked to one thing type makes the per-card "Type = X" row
  // redundant — hide it (an allowlist of one).
  const singleType = (collection.allowed_thing_types || []).length === 1;
  // Whether the calendar download has anything to offer: only date-based
  // things (loans, rentals, on-site reservations) ever reach that CSV. The
  // allowlist says so directly; an old collection with no allowlist never
  // restricted anything, so its own things are the answer — a RENT drill in a
  // restriction-free group is as bookable as one the list names.
  const allowedTypes = collection.allowed_thing_types || [];
  const hasDateThings =
    allowedTypes.length > 0
      ? allowedTypes.some((type) => DATE_TYPES.includes(type))
      : collection.things.some((thg) => DATE_TYPES.includes(thg.type));

  // When the owner has given the group its own web address, the hero's back
  // link goes there instead of the OIUEEI home — but it still says "Home"
  // (CA, 2026-09-21). `sanitizeUrl` returns "#" for anything that isn't
  // http(s), and we ignore that.
  const homePageUrl = collection.home_page ? sanitizeUrl(collection.home_page) : '';
  const backHref = homePageUrl && homePageUrl !== '#' ? homePageUrl : null;

  return (
    <div
      className="form-page"
      style={tc.color_02 ? { backgroundColor: `var(--color-${tc.color_02})` } : undefined}
    >
      <div
        className={`form-hero${collection.thumbnail_url ? ' form-hero--photo' : ''}`}
        style={tc.color_03 ? { backgroundColor: `var(--color-${tc.color_03})` } : undefined}
      >
        <div className="form-hero-split">
          <div
            className="form-hero-content"
            style={tc.color_05 ? { '--hero-text-color': `var(--color-${tc.color_05})` } : undefined}
          >
            <span className="hero-corners">
              <AccountMenu />
              {/* The group's own options (CA, 2026-10-03): curators only,
                  between the account menu and the share one. */}
              {isCurator && (
                <CollectionMenu code={code} hasDateThings={hasDateThings} downloads={downloads} />
              )}
              {canShare && (
                <ShareCollectionMenu
                  collectionCode={code}
                  collectionHeadline={headline}
                  isPublic={collection.visibility === 'PUBLIC'}
                />
              )}
              <ContactCorner />
            </span>
            {/* Says "← Home" whatever it points at (CA, 2026-09-21): the group's own
                `home_page` when it has one, the app's home otherwise. It used to be
                worded "The group's site" with an external-link icon; the wording
                and the icon went, the destination stayed. */}
            <BackLink to="/" href={backHref} label={t('common.home')} />
            <h1 className="form-hero-title">
              {headline}
              {isCurator && collection.mode === 'COMMUNITY' && (
                <>
                  {' '}
                  <Tag theme={tagTheme}>{t('collectionPage.communityTag')}</Tag>
                </>
              )}
              {isCurator && (
                <>
                  {' '}
                  <Tag theme={tagTheme}>
                    {collection.visibility === 'PUBLIC'
                      ? t('visibility.publicTag')
                      : t('visibility.privateTag')}
                  </Tag>
                </>
              )}
            </h1>
            {collection.description && (
              <MarkdownText text={L(collection.description)} className="form-hero-text" />
            )}
            {/* Attribution. With co-curators, one line names the whole team,
                founder first, everyone at the same level and shown to everyone
                (2026-09); whoever has no name is counted at the end, not
                linked, and with nobody named there is no line. Without, the
                single founder line, and only to non-owners — the owner knows
                who they are. */}
            {collection.co_owners?.length > 0
              ? namedTeam.length > 0 && (
                  <p className="form-hero-text" style={{ fontSize: 'var(--fontsize-body-m)' }}>
                    <strong>{t('collectionPage.curatorsLabel')}</strong>{' '}
                    {namedTeam.map((c, i) => (
                      <span key={c.code}>
                        {i > 0 && ', '}
                        <Link to={`/${c.code}`} className="owner-link">
                          {c.name}
                        </Link>
                      </span>
                    ))}
                    {unnamedTeamCount > 0 &&
                      ` ${t('collectionPage.curatorsMore', { count: unnamedTeamCount })}`}
                  </p>
                )
              : !isOwner &&
                collection.owner_name && (
                  <p className="form-hero-text" style={{ fontSize: 'var(--fontsize-body-m)' }}>
                    <strong>{t('collectionPage.curator')}</strong>{' '}
                    <Link to={`/${collection.owner}`} className="owner-link">
                      {collection.owner_name}
                    </Link>
                  </p>
                )}
            {/* The group's welcome PDF used to exist only in the one email a
                member gets on joining: delete that, and it was gone. The API
                serves its URL to curators and members only, so its presence is
                the whole condition. */}
            {collection.welcome_doc_url && (
              <p className="invite-nudge">
                <a
                  href={collection.welcome_doc_url}
                  className="owner-link"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {t('collectionPage.welcomeDoc')}
                </a>
              </p>
            )}
            {/* A signed-out reader used to get a one-line "This group shares its
              things on OIUEEI. Join to take part →" here; it was removed (CA,
              2026-09-21). They still reach /collections/:code/join from the
              action button on any card (login-to-act) — but not from an empty
              group, which has no card to click. */}
            {/* An invitation for a reader who is already signed in. They
              cannot be sent down the anonymous funnel — it asks for an email and
              answers with a magic link — so they get the action itself. Only on
              a PUBLIC collection: a private one is unreachable without an
              invitation, and this is exactly where the page used to offer
              "Add thing" to someone the API would refuse. */}
            {isAuthenticated &&
              !isCurator &&
              !collection.is_member &&
              collection.visibility === 'PUBLIC' && (
                <div className="invite-nudge">
                  <div>
                    <Button style={btnStyle} disabled={joining} onClick={handleJoin}>
                      {joining ? t('joinToAct.joining') : t('collectionPage.visitorJoin')}
                    </Button>
                  </div>
                  {joinError && (
                    <p role="alert" style={{ color: 'var(--color-error)', marginBottom: 0 }}>
                      {t('collectionPage.visitorJoinError')}
                    </p>
                  )}
                </div>
              )}
            {isCurator && (
              <>
                <div className="spacer-m"></div>
                {/* The row holds "Edit collection" alone (CA, 2026-10-03):
                    "Add thing", "Manage members" and the three downloads live
                    in the collection menu in the corner; the outcome of a
                    download lands right under the row. */}
                <div className="button-row-wide">
                  <ButtonLink to={`/collections/${code}/edit`} style={btnStyle}>
                    {t('collectionPage.editCollection')}
                  </ButtonLink>
                </div>
                <CollectionDownloadsStatus downloads={downloads} />
                <div className="spacer-s"></div>
                {/* Cold-start nudge (DESIGN §2/§6): the owner has something worth
                showing but hasn't invited anyone — a quiet one-line pointer, no
                banner or pressure. It disappears once the first guest joins. */}
                {collection.invites.length === 0 && visibleThings.length > 0 && (
                  <p className="invite-nudge">
                    {t('collectionPage.inviteNudge')}{' '}
                    <Link to={`/collections/${code}/invites`} className="owner-link">
                      {t('collectionPage.inviteNudgeLink')}
                    </Link>
                  </p>
                )}
              </>
            )}
            {/* Everything in here is a rank-and-file member's control —
              contributing a thing, recommending a guest — so membership
              (excluding a curator, who has the real thing above) is the single
              condition. It used to admit any signed-in reader of a COMMUNITY
              collection, which is how the dead-end button got here. */}
            {isAuthenticated && !isOwner && collection.is_member && (
              <>
                <div className="spacer-m"></div>
                {/* One row, each button on its own condition (CA, 2026-10-03):
                "Invite someone" first and primary — it opens the recommend form
                below the row, and stays on screen while the form is open so the
                same button closes it — then "Add thing", secondary. Neither:
                no row. Membership, not just mode, for "Add thing":
                `Collection.can_add_thing` requires an invite, so offering it to
                a signed-in non-member sent them through the whole form — photos
                uploaded to the bucket and all — to collect a 403 at the end.
                They get the join button above instead, which is the thing that
                actually unlocks it. */}
                {(collection.allow_member_proposals || collection.mode === 'COMMUNITY') && (
                  <div className="button-row-wide">
                    {collection.allow_member_proposals && (
                      <Button
                        ref={recommendButtonRef}
                        style={btnStyle}
                        aria-expanded={recommendOpen}
                        aria-controls={recommendOpen ? RECOMMEND_BOX_ID : undefined}
                        onClick={() => setRecommendOpen((open) => !open)}
                      >
                        {t('recommend.openButton')}
                      </Button>
                    )}
                    {collection.mode === 'COMMUNITY' && (
                      <ButtonLink to={`/collections/${code}/add`} style={btnSecondaryStyle}>
                        {t('collectionPage.addThing')}
                      </ButtonLink>
                    )}
                  </div>
                )}
                {collection.allow_member_proposals && recommendOpen && (
                  <RecommendGuest
                    id={RECOMMEND_BOX_ID}
                    collectionCode={code}
                    ownerName={collection.owner_name}
                    coOwnerCount={collection.co_owners?.length ?? 0}
                    onClose={() => {
                      setRecommendOpen(false);
                      recommendButtonRef.current?.focus();
                    }}
                  />
                )}
                {/* "Leave the group" used to sit here, third in a stack of
                unlabelled text links under the description — and the only
                destructive one of the three. It moved to the own profile's "My
                groups" list (design round): leaving is something you do to your
                own membership, so it belongs with the rest of your account, next
                to the other memberships you might weigh it against. The route
                (/collections/:code/leave) is unchanged. */}
              </>
            )}
          </div>
        </div>
        {collection.thumbnail_url && (
          <HeroPhoto
            photoUrl={collection.thumbnail_url}
            alt={headline}
            koroType={koro}
            color03={tc.color_03}
          />
        )}
        <Koros
          className="form-hero-koros"
          type={koro}
          style={tc.color_02 ? { fill: `var(--color-${tc.color_02})` } : undefined}
        />
      </div>
      <div className="page-container">
        {collection.is_onboarding && <DemoNotice />}
        {/* Each viewer's own notifications for this collection — a hold request or a
          FAQ question is answered on the thing, so it should reach whoever owns
          that thing where it actually lives, not only on Home. The endpoint always
          scopes to `request.user`, so a member sees only their own (e.g. a
          COMMUNITY contribution's own booking requests) — never a co-member's or
          the owner's. Gated on membership rather than `isOwner` alone: in
          PROPRIETARY mode that was the same person, but a COMMUNITY member who
          owns a thing here is not the collection owner and was missing this
          entirely, stranded on Home. A co-owner needs it too — `isCurator`
          covers them alongside `is_member`. */}
        {(isCurator || collection.is_member) && <InboxNotifications collection={code} />}
        {isCurator && collection.status === 'INACTIVE' && (
          <Notification
            label={t('common.notice')}
            type="info"
            style={{ marginBottom: 'var(--spacing-m)' }}
          >
            {t('collectionPage.inactiveNotice')}
          </Notification>
        )}
        {collection.is_paused && (
          <Notification
            label={t('pause.bannerLabel')}
            type="alert"
            style={{ marginBottom: 'var(--spacing-m)' }}
          >
            {collection.pause_message}
          </Notification>
        )}

        {/* Visually hidden, still in the outline (CA, 2026-09-21). The cards
            below are <h3>s (ThingLinkbox's default) and rely on an <h2> above
            them: take this out and the page jumps from <h1> to <h3>, which axe's
            heading-order flags. It also stays a landmark a screen-reader user can
            jump to, next to "Messages to the group". */}
        <h2 className="sr-only">{t('collectionPage.things')}</h2>
        <div className="spacer-m" />
        {/* A recorded DESIGN §1 exception, not an oversight: these are plain
            `<button aria-pressed>`s, not HDS `Tag`. HDS `Tag` (`variant="action"`)
            has no pressed/selected state to bind `aria-pressed` to, and a filter
            chip has to announce which one is active. The `.tag-chip` styling is
            ours; it sits on the same page as real HDS `Tag`s (`ThingTags`, on
            every card below), so the two are free to drift apart visually —
            worth knowing if either one's look changes (found in review,
            2026-09-18). */}
        {visibleThings.length > 0 && collectionTags.length > 0 && (
          <div className="tag-filter-bar">
            <button
              type="button"
              className="tag-chip"
              aria-pressed={!effectiveTag}
              onClick={() => {
                setActiveTag(null);
                setShownCount(CARDS_PER_PAGE);
              }}
            >
              {t('collectionPage.allTags')} ({visibleThings.length})
            </button>
            {collectionTags.map((tag) => {
              const count = visibleThings.filter((thg) => (thg.tags || []).includes(tag)).length;
              return (
                <button
                  key={tag}
                  type="button"
                  className="tag-chip"
                  aria-pressed={effectiveTag === tag}
                  onClick={() => {
                    setActiveTag(effectiveTag === tag ? null : tag);
                    setShownCount(CARDS_PER_PAGE);
                  }}
                >
                  {L(tag)} ({count})
                </button>
              );
            })}
          </div>
        )}
        {visibleThings.length === 0 ? (
          <>
            <p>
              {t('collectionPage.noThings')}
              {canAddThing && (
                <>
                  {' '}
                  <Link to={`/collections/${code}/add`}>{t('collectionPage.addOne')}</Link>.
                </>
              )}
            </p>
            <div className="spacer-xxs" />
            {canAddThing && (
              <p>
                <Link to={`/collections/${code}/add#bulk-add`}>
                  {t('collectionPage.addManyCsv')}
                </Link>
              </p>
            )}
          </>
        ) : shownThings.length === 0 ? (
          <p>{t('collectionPage.noThingsForTag')}</p>
        ) : (
          <>
            <div className="things-grid">
              {shownThings.map((thing) => (
                <ThingLinkbox
                  key={thing.code}
                  thing={thing}
                  userCode={userCode}
                  collectionCode={code}
                  collectionHeadline={headline}
                  collectionOwner={collection.owner}
                  collectionMode={collection.mode}
                  isPaused={collection.is_paused}
                  hideType={singleType}
                  canAct={isAuthenticated}
                  loginToAct={!isAuthenticated}
                  onUpdateThing={handleUpdateThing}
                />
              ))}
            </div>
            {remainingThings > 0 && (
              <>
                <div className="spacer-m" />
                <Button
                  variant="secondary"
                  style={btnSecondaryStyle}
                  onClick={() => setShownCount((n) => n + CARDS_PER_PAGE)}
                >
                  {t('collectionPage.showMoreThings', { count: remainingThings })}
                </Button>
              </>
            )}
          </>
        )}
        {/* A way in for a signed-out reader where no button leads there (see
            `anonJoinKey`): under "No things in this collection yet." in an empty
            group, and under the grid — after "Show more" — of a COMMUNITY one.
            Not in the hero (CA removed that line on 2026-09-21), and it goes to
            the group's join page with no ?thing=: there is no thing in it. */}
        {anonJoinKey && (
          <p className="invite-nudge">
            <Link to={`/collections/${code}/join`}>{t(anonJoinKey)}</Link>
          </p>
        )}

        {isCurator && collection.invites.length > 0 && (
          <>
            <div className="spacer-l" />
            <h2>{t('broadcast.heading')}</h2>
            <div className="spacer-m" />
            {!broadcastOpen ? (
              <Button
                variant="secondary"
                style={btnSecondaryStyle}
                onClick={() => setBroadcastOpen(true)}
              >
                {t('broadcast.openButton')}
              </Button>
            ) : (
              <div className="form-grid">
                {/* The one place in the product where a member learns an address
                  the API takes care never to serve them: the broadcast carries
                  the owner's own email as Reply-To, so replying to the group
                  message is one tap. Worth keeping — without it a broadcast is
                  a megaphone with no way back, and the replies would land on a
                  noreply — but not worth doing without saying so first
                  (DESIGN §6). Their own address, their own send: disclosure is
                  what consent needs here, not a switch. */}
                <TextArea
                  id="broadcast-message"
                  label={t('broadcast.messageLabel')}
                  helperText={t('broadcast.replyToNotice')}
                  value={broadcastMessage}
                  onChange={(e) => setBroadcastMessage(e.target.value)}
                  maxLength={256}
                  required
                />
                <StatusRegion>
                  {broadcastResult && (
                    <Notification
                      label={
                        broadcastResult.type === 'success' ? t('common.sent') : t('common.error')
                      }
                      type={broadcastResult.type}
                      style={{ marginBottom: 'var(--spacing-s)' }}
                      dismissible
                      closeButtonLabelText={t('common.close')}
                      onClose={() => setBroadcastResult(null)}
                    >
                      {broadcastResult.message}
                    </Notification>
                  )}
                </StatusRegion>
                <div className="button-row-wide">
                  <Button
                    style={btnStyle}
                    onClick={handleBroadcast}
                    disabled={broadcastSending || !broadcastMessage.trim()}
                  >
                    {broadcastSending ? t('broadcast.sending') : t('broadcast.sendButton')}
                  </Button>
                  <Button
                    variant="secondary"
                    style={btnSecondaryStyle}
                    onClick={() => {
                      setBroadcastOpen(false);
                      setBroadcastResult(null);
                    }}
                  >
                    {t('common.close')}
                  </Button>
                </div>
              </div>
            )}
          </>
        )}

        {/* Gated on the payload, not on `isOwner` (the *collection* owner): the
            backend now sends an INACTIVE thing to two audiences — the
            collection owner (every one) and that thing's own owner (just
            theirs), the same "owner can always view their own things" rule
            `Thing.can_view()` already states. In a COMMUNITY collection a
            member's own gift going INACTIVE after a completed hand-off, or a
            listing they hid themselves, must stay reachable from here — not
            only via the thing's own `/things/{code}` URL — same as it always
            has for the collection owner. */}
        {collection.things.some((thg) => thg.status === 'INACTIVE') && (
          <>
            <div className="spacer-l" />
            <h2>{t('collectionPage.inactiveThings')}</h2>
            <div className="spacer-m" />
            <div className="things-grid">
              {[...collection.things]
                .filter((thg) => thg.status === 'INACTIVE')
                .sort((a, b) => {
                  return new Date(b.created) - new Date(a.created);
                })
                .map((thing) => (
                  <ThingLinkbox
                    key={thing.code}
                    thing={thing}
                    userCode={userCode}
                    collectionCode={code}
                    collectionHeadline={headline}
                    collectionOwner={collection.owner}
                    collectionMode={collection.mode}
                    hideType={singleType}
                    onUpdateThing={handleUpdateThing}
                  />
                ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

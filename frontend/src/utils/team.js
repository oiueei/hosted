/**
 * Who runs a collection, in the one order and with the one rule every place that
 * names them follows: the founder first, then the co-curators; those with a name
 * are named, those without are only counted — at the end.
 *
 * The API sends a person's bare `name`, never an email standing in for it (the
 * email is withheld from co-members, L2), so someone who set none arrives as
 * `''`. Listing them would leave a gap — "Oriol, ," — so they are counted
 * instead ("and 2 more people", `collectionPage.curatorsMore`), the founder
 * included. And with nobody named there is nothing to say at all.
 *
 * `CollectionPage`'s "Run by:" line (which links each name) and the "Run by"
 * column of "My groups" on the own profile (plain text) both read it, so the two
 * cannot come to disagree about who is on the team or how it is written
 * (CA, 2026-10-03).
 */
export function collectionTeam(collection) {
  const team = [
    { code: collection.owner, name: collection.owner_name },
    ...(collection.co_owners ?? []),
  ];
  const named = team.filter((member) => member.name);
  return { named, unnamedCount: team.length - named.length };
}

/**
 * The team as one line of plain text — "Oriol, Lili and 2 more people" — or `''`
 * when nobody has a name. The same words as the hero's line, minus the links.
 */
export function teamText(collection, t) {
  const { named, unnamedCount } = collectionTeam(collection);
  if (named.length === 0) return '';
  const names = named.map((member) => member.name).join(', ');
  return unnamedCount > 0
    ? `${names} ${t('collectionPage.curatorsMore', { count: unnamedCount })}`
    : names;
}

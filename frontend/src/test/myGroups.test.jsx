import { act, render, screen, within } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { MemoryRouter, Routes, Route } from 'react-router';
import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

expect.extend(toHaveNoViolations);

window.scrollTo = vi.fn();

vi.mock('../services/api', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'mock-csrf'),
}));

import { apiFetch } from '../services/api';
import UserPage from '../pages/UserPage';
import { mockMatchMedia, PHONE } from './matchMedia';

const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

const ME = {
  code: 'ME0001',
  name: 'Carlos',
  email: 'me@test.com',
  koro: 'basic',
  created: '2026-01-01',
};
const OTHER = { code: 'OTH001', name: 'Lili', created: '2026-01-01', shared_collections: [] };

const setApi = ({ memberships = [], profile = ME, invitedOk = true } = {}) => {
  apiFetch.mockImplementation((url) => {
    if (url.startsWith('/api/v1/invited-collections/')) {
      return invitedOk
        ? ok(memberships)
        : Promise.resolve({ ok: false, status: 500, json: async () => ({}) });
    }
    return ok(profile);
  });
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('userCode', 'ME0001');
  vi.clearAllMocks();
});

const renderOwn = () =>
  render(
    <MemoryRouter>
      <UserPage />
    </MemoryRouter>
  );
const renderOther = () =>
  render(
    <MemoryRouter initialEntries={['/OTH001']}>
      <Routes>
        <Route path="/:userCode" element={<UserPage />} />
      </Routes>
    </MemoryRouter>
  );

/**
 * "My groups" on the own profile — where leaving a group lives now.
 *
 * It used to be a link in the collection hero, third in a stack of unlabelled
 * text links under the description and the only destructive one of the three.
 * Leaving is something you do to your own membership, so it belongs with the
 * rest of your account, beside the other memberships you might weigh it against.
 */
describe('UserPage — My groups', () => {
  // A row of the table, found by the group's name.
  const rowOf = (name) => screen.getByRole('link', { name }).closest('tr');

  test('lists the groups I belong to, each with its own way out', async () => {
    setApi({
      memberships: [
        { code: 'COL001', headline: "Lili's Lending Library" },
        { code: 'COL002', headline: "Lolo's Leafy Lounge" },
      ],
    });

    renderOwn();

    expect(await screen.findByRole('heading', { name: /my groups/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: "Lili's Lending Library" })).toHaveAttribute(
      'href',
      '/collections/COL001'
    );
    const leaveLinks = screen.getAllByRole('link', { name: /leave the group/i });
    expect(leaveLinks).toHaveLength(2);
    expect(leaveLinks[0]).toHaveAttribute('href', '/collections/COL001/leave');
  });

  test('is a table of three columns: the group, who runs it, and a nameless one for the way out', async () => {
    // The same HDS Table as the request pages. The last header
    // is named for a screen reader only, so the column is not an empty <th>.
    setApi({ memberships: [{ code: 'COL001', headline: 'Bibliocoses' }] });

    renderOwn();

    const table = await screen.findByRole('table', { name: 'My groups' });
    expect(
      within(table)
        .getAllByRole('columnheader')
        .map((th) => th.textContent)
    ).toEqual(['Group', 'Run by', 'Actions']);
    const [group, , actions] = within(rowOf('Bibliocoses')).getAllByRole('cell');
    expect(within(group).getByRole('link', { name: 'Bibliocoses' })).toBeInTheDocument();
    expect(within(actions).getByRole('link', { name: /leave the group/i })).toHaveAttribute(
      'href',
      '/collections/COL001/leave'
    );
  });

  test('the team column names the founder first, then the co-curators, joined by "and", as plain text', async () => {
    setApi({
      memberships: [
        {
          code: 'COL001',
          headline: 'Bibliocoses',
          owner: 'OWN001',
          owner_name: 'Lili',
          co_owners: [{ code: 'CO0001', name: 'Lolo' }],
        },
      ],
    });

    renderOwn();

    await screen.findByRole('table', { name: 'My groups' });
    const team = within(rowOf('Bibliocoses')).getAllByRole('cell')[1];
    expect(team).toHaveTextContent(/^Lili and Lolo$/);
    // The hero links each name; here it is text.
    expect(within(team).queryByRole('link')).toBeNull();
  });

  test('someone with no name is counted after the names, never left as a gap', async () => {
    setApi({
      memberships: [
        {
          code: 'COL001',
          headline: 'Bibliocoses',
          owner: 'OWN001',
          owner_name: 'Lili',
          co_owners: [
            { code: 'CO0001', name: '' },
            { code: 'CO0002', name: 'Lolo' },
          ],
        },
      ],
    });

    renderOwn();

    await screen.findByRole('table', { name: 'My groups' });
    const team = within(rowOf('Bibliocoses')).getAllByRole('cell')[1];
    expect(team).toHaveTextContent(/^Lili, Lolo, and 1 more person$/);
  });

  test('a group whose team has no names leaves the cell empty', async () => {
    setApi({
      memberships: [
        { code: 'COL001', headline: 'Bibliocoses', owner: 'OWN001', owner_name: '', co_owners: [] },
      ],
    });

    renderOwn();

    await screen.findByRole('table', { name: 'My groups' });
    expect(within(rowOf('Bibliocoses')).getAllByRole('cell')[1]).toHaveTextContent(/^$/);
  });

  test('the table has no axe violations', async () => {
    setApi({
      memberships: [
        {
          code: 'COL001',
          headline: 'Bibliocoses',
          owner: 'OWN001',
          owner_name: 'Lili',
          co_owners: [{ code: 'CO0001', name: 'Lolo' }],
        },
      ],
    });

    const { container } = renderOwn();
    await screen.findByRole('table', { name: 'My groups' });

    expect(await axe(container)).toHaveNoViolations();
  });

  test('a localized group name is resolved, never raw JSON', async () => {
    setApi({
      memberships: [
        { code: 'COL003', headline: '{"en": "Mum\'s things", "es": "Las cosas de mamá"}' },
      ],
    });

    renderOwn();

    expect(await screen.findByRole('link', { name: "Mum's things" })).toBeInTheDocument();
    expect(screen.queryByText(/\{"en"/)).not.toBeInTheDocument();
  });

  test('belonging to nothing shows no section at all', async () => {
    setApi({ memberships: [] });

    renderOwn();

    await screen.findByText(/Carlos/);
    expect(screen.queryByRole('heading', { name: /my groups/i })).not.toBeInTheDocument();
  });

  test('a failed fetch costs the section, never the profile', async () => {
    setApi({ memberships: [], invitedOk: false });

    renderOwn();

    // The profile still renders; only the groups list is absent.
    expect(await screen.findByText(/Carlos/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /my groups/i })).not.toBeInTheDocument();
  });

  test("somebody else's profile never shows my memberships", async () => {
    setApi({ memberships: [{ code: 'COL001', headline: 'Private business' }], profile: OTHER });

    renderOther();

    // Their profile, rendered — the assertion is about what is absent from it.
    await screen.findByText(/don't share any groups/i);
    expect(screen.queryByRole('heading', { name: /my groups/i })).not.toBeInTheDocument();
    expect(screen.queryByText('Private business')).not.toBeInTheDocument();
  });
});

/**
 * UserPage builds its own hero rather than using PageLayout, so it derives the
 * theeeme button styles itself. It hand-rolled them for a long time and omitted
 * the `*-focus` pins that stop HDS repainting a button when the keyboard reaches
 * it — a suomenlinna/engel theeeme turned its light button a different colour
 * under focus, exactly when it had to stay readable. It now goes through
 * `useTheeeme`, which pins them.
 */
describe('UserPage — the hero action buttons carry the full theeeme', () => {
  const THEEEME = {
    color_01: 'engel',
    color_02: 'bus-medium-light',
    color_03: 'copper',
    color_04: 'black',
    color_05: 'black',
    color_06: 'black',
  };

  test('own profile: the buttons are themed from the fetched colours', async () => {
    setApi({ profile: { ...ME, theeeme_colors: THEEEME } });
    renderOwn();

    const edit = await screen.findByRole('link', { name: /edit profile/i });
    // engel is a light accent — white text on it is 1.22:1. The primary style
    // pairs color_06 with color_01, the pairing paletteContrast.test.js pins at
    // >= 4.5:1 for every palette.
    expect(edit.style.getPropertyValue('--background-color')).toBe('var(--color-engel)');
    expect(edit.style.getPropertyValue('--color')).toBe('var(--color-black)');
  });

  test('own profile: focus does not recolour a button — the *-focus tokens are pinned', async () => {
    setApi({ profile: { ...ME, theeeme_colors: THEEEME } });
    renderOwn();

    const edit = await screen.findByRole('link', { name: /edit profile/i });
    const logout = screen.getByRole('link', { name: /log ?out/i });
    for (const btn of [edit, logout]) {
      expect(btn.style.getPropertyValue('--background-color-focus')).toBe(
        btn.style.getPropertyValue('--background-color')
      );
      expect(btn.style.getPropertyValue('--color-focus')).toBe(
        btn.style.getPropertyValue('--color')
      );
      expect(btn.style.getPropertyValue('--outline-color-focus')).toBe('var(--color-black)');
    }
  });
});

/**
 * On a phone each group is a card instead of a row (`ResponsiveTable`): in a table, "Leave the group" broke word by word down a 100px
 * column. The same cells, in the same order, with "Run by:" in front of the team
 * (the table has it as a header) and the way out on the right.
 */
describe('My groups on a phone', () => {
  let media;
  beforeEach(() => {
    media = mockMatchMedia({ [PHONE]: true });
  });
  afterEach(() => media.restore());

  const group = {
    code: 'COL001',
    headline: 'Bibliocoses',
    owner: 'OWN001',
    owner_name: 'Lili',
    co_owners: [{ code: 'CO0001', name: 'Lolo' }],
  };

  test('a group is a card: its name, "Run by:" and who, and the way out', async () => {
    setApi({ memberships: [group] });
    renderOwn();

    const list = await screen.findByRole('list', { name: 'My groups' });
    expect(screen.queryByRole('table')).toBeNull();
    const [card] = within(list).getAllByRole('listitem');
    expect(within(card).getByRole('link', { name: 'Bibliocoses' })).toHaveAttribute(
      'href',
      '/collections/COL001'
    );
    expect(within(card).getByText('Run by:')).toBeInTheDocument();
    expect(within(card).getByText('Lili and Lolo')).toBeInTheDocument();
    expect(within(card).getByRole('link', { name: /leave the group/i })).toHaveAttribute(
      'href',
      '/collections/COL001/leave'
    );
  });

  test('the name comes first and the way out last, on the right', async () => {
    setApi({ memberships: [group] });
    renderOwn();

    const [card] = within(await screen.findByRole('list', { name: 'My groups' })).getAllByRole(
      'listitem'
    );
    const [first, , last] = [...card.children];
    expect(within(first).getByRole('link', { name: 'Bibliocoses' })).toBeInTheDocument();
    expect(within(last).getByRole('link', { name: /leave the group/i })).toBeInTheDocument();
    expect(last.firstElementChild).toHaveStyle({ justifyContent: 'flex-end' });
  });

  test('a group whose team has no names has no empty "Run by:" line', async () => {
    setApi({ memberships: [{ ...group, owner_name: '', co_owners: [] }] });
    renderOwn();

    const list = await screen.findByRole('list', { name: 'My groups' });
    expect(within(list).queryByText('Run by:')).toBeNull();
    expect(within(list).getByRole('link', { name: /leave the group/i })).toBeInTheDocument();
  });

  test('the cards have no axe violations', async () => {
    setApi({ memberships: [group, { ...group, code: 'COL002', headline: 'Otra' }] });
    const { container } = renderOwn();
    await screen.findByRole('list', { name: 'My groups' });

    expect(await axe(container)).toHaveNoViolations();
  });
});

/**
 * The team of a group is written as the language writes a list:
 * "Lili y Lolo", "Lili, Lolo y 2 personas más" — the same line the collection's hero
 * has, without the links (`utils/team.js`). The count of those without a name is the
 * last element of the list, so its text carries no conjunction of its own.
 */
describe('UserPage — My groups: the team in the language on screen', () => {
  afterEach(async () => {
    // Put the language back so the next test starts in English.
    const { default: i18n } = await import('../i18n');
    // The page is still mounted when this runs: the change is an update to it.
    await act(async () => {
      await i18n.changeLanguage('en');
    });
    localStorage.removeItem('i18nextLng');
  });

  const named = (...names) => names.map((name, i) => ({ code: `CO000${i + 1}`, name }));
  const nameless = (n) => Array.from({ length: n }, (_, i) => ({ code: `CO009${i}`, name: '' }));

  // The founder is "Lili" in every case.
  const CASES = [
    ['en', 'two names', named('Lolo'), 'Lili and Lolo'],
    ['en', 'three names', named('Lolo', 'Abel'), 'Lili, Lolo, and Abel'],
    [
      'en',
      'two names and two without',
      [...named('Lolo'), ...nameless(2)],
      'Lili, Lolo, and 2 more people',
    ],
    ['en', 'one name and one without', nameless(1), 'Lili and 1 more person'],
    ['es', 'two names', named('Lolo'), 'Lili y Lolo'],
    ['es', 'three names', named('Lolo', 'Abel'), 'Lili, Lolo y Abel'],
    [
      'es',
      'two names and two without',
      [...named('Lolo'), ...nameless(2)],
      'Lili, Lolo y 2 personas más',
    ],
    ['es', 'one name and one without', nameless(1), 'Lili y 1 persona más'],
    ['ca', 'two names', named('Lolo'), 'Lili i Lolo'],
    ['ca', 'three names', named('Lolo', 'Abel'), 'Lili, Lolo i Abel'],
    [
      'ca',
      'two names and two without',
      [...named('Lolo'), ...nameless(2)],
      'Lili, Lolo i 2 persones més',
    ],
    ['ca', 'one name and one without', nameless(1), 'Lili i 1 persona més'],
  ].map(([language, what, co_owners, expected]) => ({ language, what, co_owners, expected }));

  test.each(CASES)(
    'in $language, $what: "$expected"',
    async ({ language, co_owners, expected }) => {
      const { default: i18n } = await import('../i18n');
      await i18n.changeLanguage(language);
      setApi({
        memberships: [
          {
            code: 'COL001',
            headline: 'Bibliocoses',
            owner: 'OWN001',
            owner_name: 'Lili',
            co_owners,
          },
        ],
      });

      renderOwn();

      const row = (await screen.findByRole('link', { name: 'Bibliocoses' })).closest('tr');
      const team = within(row).getAllByRole('cell')[1];
      expect(team.textContent).toBe(expected);
      // Plain text: the profile page links nobody here.
      expect(within(team).queryByRole('link')).toBeNull();
    }
  );
});

// The group's name and "Leave the group" are bold links: one rule
// in App.css for the text links inside the component's own class, `.responsive-table`
// — see `test/tableLinkWeight.test.jsx`. "Leave the group" keeps its muted class (size
// and grey) and is only bolder. These pin that both are inside it, in the table and in
// the cards.
describe('UserPage — the bold links of My groups', () => {
  const SELECTOR = ".responsive-table a:not([class*='hds-button'])";
  const groups = [{ code: 'COL001', headline: 'Bibliocoses', owner: 'OWN001', owner_name: 'Lili' }];

  test('the group’s link and the way out are inside the component’s class, in the table', async () => {
    setApi({ memberships: groups });
    renderOwn();

    const group = await screen.findByRole('link', { name: 'Bibliocoses' });
    const leave = screen.getByRole('link', { name: /leave the group/i });
    expect(group.matches(SELECTOR)).toBe(true);
    expect(leave.matches(SELECTOR)).toBe(true);
    // The way out keeps its muted class: the weight is the rule's, size and grey its own.
    expect(leave).toHaveClass('table-cell-link--muted');
  });

  test('and in the cards of a phone', async () => {
    const media = mockMatchMedia({ [PHONE]: true });
    try {
      setApi({ memberships: groups });
      renderOwn();

      const group = await screen.findByRole('link', { name: 'Bibliocoses' });
      const leave = screen.getByRole('link', { name: /leave the group/i });
      expect(group.matches(SELECTOR)).toBe(true);
      expect(leave.matches(SELECTOR)).toBe(true);
      expect(leave).toHaveClass('table-cell-link--muted');
    } finally {
      media.restore();
    }
  });
});

import { describe, test, expect } from 'vitest';
import { collectionTeam, teamParts, teamText } from './team';

// A stand-in for `t` that shows the key and the count, so the rule is tested
// apart from any language's wording.
const t = (key, options) => (options?.count !== undefined ? `<${key}:${options.count}>` : key);

const group = (over = {}) => ({
  owner: 'OWN001',
  owner_name: 'Lili',
  co_owners: [],
  ...over,
});

describe('collectionTeam', () => {
  test('a group with no co-curators is its founder alone', () => {
    expect(collectionTeam(group())).toEqual({
      named: [{ code: 'OWN001', name: 'Lili' }],
      unnamedCount: 0,
    });
  });

  test('a field the API left out is no co-curators, not a crash', () => {
    expect(collectionTeam({ owner: 'OWN001', owner_name: 'Lili' }).named).toHaveLength(1);
  });

  test('the founder comes first, then the co-curators in the order given', () => {
    const { named } = collectionTeam(
      group({
        co_owners: [
          { code: 'CO0001', name: 'Zoe' },
          { code: 'CO0002', name: 'Abel' },
        ],
      })
    );

    expect(named.map((member) => member.name)).toEqual(['Lili', 'Zoe', 'Abel']);
  });

  test('someone with no name is counted, not listed — the founder included', () => {
    const { named, unnamedCount } = collectionTeam(
      group({
        owner_name: '',
        co_owners: [
          { code: 'CO0001', name: 'Zoe' },
          { code: 'CO0002', name: '' },
        ],
      })
    );

    expect(named.map((member) => member.name)).toEqual(['Zoe']);
    expect(unnamedCount).toBe(2);
  });

  test('it does not touch the collection it reads', () => {
    const co_owners = [{ code: 'CO0001', name: 'Zoe' }];
    collectionTeam(group({ co_owners }));
    expect(co_owners).toEqual([{ code: 'CO0001', name: 'Zoe' }]);
  });
});

const MORE = (n) => `<collectionPage.curatorsMore:${n}>`;
const pair = (...names) => names.map((name, i) => ({ code: `CO000${i + 1}`, name }));
const nameless = (n) => Array.from({ length: n }, (_, i) => ({ code: `CO009${i}`, name: '' }));

describe('teamText', () => {
  test('names the founder alone, as plain text', () => {
    expect(teamText(group(), t, 'en')).toBe('Lili');
  });

  // The conjunction and the commas are the language's own (`Intl.ListFormat`), in the
  // language that is on screen (CA, 2026-10-05).
  test.each([
    ['en', 'Lili and Zoe', 'Lili, Zoe, and Abel'],
    ['es', 'Lili y Zoe', 'Lili, Zoe y Abel'],
    ['ca', 'Lili i Zoe', 'Lili, Zoe i Abel'],
  ])('in %s two names are "%s" and three are "%s", founder first', (language, two, three) => {
    expect(teamText(group({ co_owners: pair('Zoe') }), t, language)).toBe(two);
    expect(teamText(group({ co_owners: pair('Zoe', 'Abel') }), t, language)).toBe(three);
  });

  test('the language changes the conjunction without changing who is named', () => {
    const team = group({ co_owners: pair('Zoe') });
    expect(teamText(team, t, 'en')).toBe('Lili and Zoe');
    expect(teamText(team, t, 'es')).toBe('Lili y Zoe');
    expect(teamText(team, t, 'ca')).toBe('Lili i Zoe');
  });

  test.each([
    ['en', `Lili, Abel, and ${MORE(2)}`, `Lili and ${MORE(1)}`],
    ['es', `Lili, Abel y ${MORE(2)}`, `Lili y ${MORE(1)}`],
    ['ca', `Lili, Abel i ${MORE(2)}`, `Lili i ${MORE(1)}`],
  ])(
    'in %s the unnamed are the last element of the list: two names and two without, one and one',
    (language, twoAndTwo, oneAndOne) => {
      expect(teamText(group({ co_owners: [...pair('Abel'), ...nameless(2)] }), t, language)).toBe(
        twoAndTwo
      );
      expect(teamText(group({ co_owners: nameless(1) }), t, language)).toBe(oneAndOne);
    }
  );

  test('counts the unnamed at the end, after the names and not as a gap between them', () => {
    expect(
      teamText(
        group({
          co_owners: [
            { code: 'CO0001', name: '' },
            { code: 'CO0002', name: 'Abel' },
          ],
        }),
        t,
        'en'
      )
    ).toBe(`Lili, Abel, and ${MORE(1)}`);
  });

  test('with nobody named there is nothing to say: an empty string, not "2 more people"', () => {
    expect(
      teamText(group({ owner_name: '', co_owners: [{ code: 'CO0001', name: '' }] }), t, 'en')
    ).toBe('');
  });

  test('a language tag the browser cannot read does not break the line', () => {
    // `new Intl.ListFormat('not a language')` throws a RangeError; the browser's own
    // default language stands in (whatever it is), and the names are still all there.
    for (const language of ['not a language', undefined]) {
      const line = teamText(group({ co_owners: pair('Zoe') }), t, language);
      expect(line.startsWith('Lili')).toBe(true);
      expect(line.endsWith('Zoe')).toBe(true);
      expect(line.length).toBeGreaterThan('LiliZoe'.length);
    }
  });
});

// The hero links each name, so it needs the pieces and not the line.
describe('teamParts', () => {
  test('is the members, the count and what the language puts between them, in order', () => {
    expect(teamParts(group({ co_owners: [...pair('Abel'), ...nameless(2)] }), t, 'en')).toEqual([
      { type: 'member', member: { code: 'OWN001', name: 'Lili' } },
      { type: 'literal', value: ', ' },
      { type: 'member', member: { code: 'CO0001', name: 'Abel' } },
      { type: 'literal', value: ', and ' },
      { type: 'more', text: MORE(2) },
    ]);
  });

  test('speaks the language it is asked for', () => {
    const parts = teamParts(group({ co_owners: pair('Zoe') }), t, 'es');
    expect(parts.map((part) => part.value ?? part.member.name)).toEqual(['Lili', ' y ', 'Zoe']);
  });

  test('two people with the same name stay two members, each with its own code', () => {
    // Matching the pieces back by their text would hand both the first one's code.
    const parts = teamParts(
      group({ owner_name: 'Ana', co_owners: [{ code: 'CO0001', name: 'Ana' }] }),
      t,
      'en'
    );
    expect(parts.filter((part) => part.type === 'member').map((part) => part.member.code)).toEqual([
      'OWN001',
      'CO0001',
    ]);
  });

  test('nobody named is no pieces at all', () => {
    expect(teamParts(group({ owner_name: '', co_owners: nameless(2) }), t, 'en')).toEqual([]);
  });

  test('the founder alone is one member and nothing around it', () => {
    expect(teamParts(group(), t, 'en')).toEqual([
      { type: 'member', member: { code: 'OWN001', name: 'Lili' } },
    ]);
  });
});

import { describe, test, expect } from 'vitest';
import { collectionTeam, teamText } from './team';

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

describe('teamText', () => {
  test('names the founder alone, as plain text', () => {
    expect(teamText(group(), t)).toBe('Lili');
  });

  test('comma-separates the names, founder first', () => {
    expect(
      teamText(
        group({
          co_owners: [
            { code: 'CO0001', name: 'Zoe' },
            { code: 'CO0002', name: 'Abel' },
          ],
        }),
        t
      )
    ).toBe('Lili, Zoe, Abel');
  });

  test('counts the unnamed at the end, after the names and not as a gap between them', () => {
    expect(
      teamText(
        group({
          co_owners: [
            { code: 'CO0001', name: '' },
            { code: 'CO0002', name: 'Abel' },
          ],
        }),
        t
      )
    ).toBe('Lili, Abel <collectionPage.curatorsMore:1>');
  });

  test('with nobody named there is nothing to say: an empty string, not "and 2 more people"', () => {
    expect(teamText(group({ owner_name: '', co_owners: [{ code: 'CO0001', name: '' }] }), t)).toBe(
      ''
    );
  });
});

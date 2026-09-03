import { describe, test, expect } from 'vitest';
import { requiredLegalEnv, inlinedLegalIdentity, missingLegalEnv } from './check-legal-env.mjs';

// Two failure modes this guard exists for: a legal notice that reads
// "**undefined** — NIF undefined" because `vite build` silently replaces a
// missing `import.meta.env` value with `undefined`, and an operator-identity
// field quietly hardcoded back as literal text in one of three languages. So
// these pin the three predicates — what the text asks for, whether a field was
// inlined, whether the environment answers — and the self-configuring case that
// lets the same `package.json` sit in the standalone repo without arming
// anything.

const TEMPLATED = [
  'export default `\n**${import.meta.env.VITE_LEGAL_OPERATOR}** — NIF ' +
    '${import.meta.env.VITE_LEGAL_NIF} — ${import.meta.env.VITE_LEGAL_ADDRESS}`;',
  'export default `\ngeneric commitment text, no interpolation`;',
];

// Operator and NIF templated, address written in as literal text.
const ADDRESS_INLINED = [
  'export default `\n**${import.meta.env.VITE_LEGAL_OPERATOR}** — NIF ' +
    '${import.meta.env.VITE_LEGAL_NIF} — A Street 26, 08038 A City`;',
];

const GENERIC = ['export default `\n# Who operates this instance\nnot completed`;'];

describe('requiredLegalEnv', () => {
  test('collects every VITE_LEGAL_ name the sources interpolate, deduped and sorted', () => {
    expect(requiredLegalEnv(TEMPLATED)).toEqual([
      'VITE_LEGAL_ADDRESS',
      'VITE_LEGAL_NIF',
      'VITE_LEGAL_OPERATOR',
    ]);
  });

  test('finds nothing in legal text that does not reference the environment', () => {
    expect(requiredLegalEnv(GENERIC)).toEqual([]);
  });
});

describe('inlinedLegalIdentity', () => {
  test('all three fields templated — nothing inlined', () => {
    expect(inlinedLegalIdentity(TEMPLATED)).toEqual([]);
  });

  test('names the field that was written in as literal text', () => {
    expect(inlinedLegalIdentity(ADDRESS_INLINED)).toEqual(['VITE_LEGAL_ADDRESS']);
  });

  test('the standalone case: no VITE_LEGAL_ reference at all is not "inlined"', () => {
    expect(inlinedLegalIdentity(GENERIC)).toEqual([]);
  });
});

describe('missingLegalEnv', () => {
  test('the standalone case: no references means nothing is required, whatever the env', () => {
    expect(missingLegalEnv(GENERIC, {})).toEqual([]);
  });

  test('all three set — build may proceed', () => {
    const env = {
      VITE_LEGAL_OPERATOR: 'A Name',
      VITE_LEGAL_NIF: 'X1234567Z',
      VITE_LEGAL_ADDRESS: 'A street, a city',
    };
    expect(missingLegalEnv(TEMPLATED, env)).toEqual([]);
  });

  test('a placeholder counts as set — the check is "is it there", not "is it real"', () => {
    const env = {
      VITE_LEGAL_OPERATOR: 'CI-PLACEHOLDER',
      VITE_LEGAL_NIF: 'CI-PLACEHOLDER',
      VITE_LEGAL_ADDRESS: 'CI-PLACEHOLDER',
    };
    expect(missingLegalEnv(TEMPLATED, env)).toEqual([]);
  });

  test('one missing var is named', () => {
    const env = { VITE_LEGAL_OPERATOR: 'A Name', VITE_LEGAL_NIF: 'X1234567Z' };
    expect(missingLegalEnv(TEMPLATED, env)).toEqual(['VITE_LEGAL_ADDRESS']);
  });

  test('a blank or whitespace-only value is treated as missing', () => {
    const env = { VITE_LEGAL_OPERATOR: '', VITE_LEGAL_NIF: '   ', VITE_LEGAL_ADDRESS: 'x' };
    expect(missingLegalEnv(TEMPLATED, env)).toEqual(['VITE_LEGAL_NIF', 'VITE_LEGAL_OPERATOR']);
  });
});

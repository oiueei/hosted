import { describe, test, expect, vi } from 'vitest';
import {
  ALLOWED,
  evaluateAudit,
  reportAudit,
  loadReport,
  main,
} from './audit-gate.mjs';

// The gate that decides whether a dependency advisory turns CI red — and, on
// purpose, the one thing in this repo that can *accept* a high. Its failure mode
// is silent and total: a bug in the severity check or the allowlist match makes
// every build green while nothing is guarded, and nobody finds out until an
// advisory that should have blocked ships to production.
//
// So these hold three things: what blocks, what is allowed to pass, and that an
// allowlist entry is a written debt rather than a way to make a red build go
// away.

const advisory = (over = {}) => ({
  source: 1234567,
  name: 'some-package',
  severity: 'high',
  title: 'Prototype pollution in some-package',
  url: 'https://github.com/advisories/GHSA-aaaa-bbbb-cccc',
  range: '<1.2.3',
  ...over,
});

/** A parsed `npm audit --json` report carrying the given advisories. */
const report = (...advisories) => ({
  vulnerabilities: Object.fromEntries(
    advisories.map((via, i) => [via.name ?? `pkg${i}`, { via: [via] }])
  ),
});

const ids = (entries) => entries.map((e) => e.id);

describe('what fails the build', () => {
  test('an unlisted high blocks', () => {
    const { blocking } = evaluateAudit(report(advisory()), {});

    expect(ids(blocking)).toEqual(['GHSA-aaaa-bbbb-cccc']);
  });

  test('a critical blocks', () => {
    const { blocking } = evaluateAudit(report(advisory({ severity: 'critical' })), {});

    expect(ids(blocking)).toEqual(['GHSA-aaaa-bbbb-cccc']);
  });

  test('moderate and low do not block — the threshold is high/critical', () => {
    const { blocking, allowed } = evaluateAudit(
      report(
        advisory({ severity: 'moderate', url: 'https://github.com/advisories/GHSA-mod-0000-0000' }),
        advisory({ severity: 'low', url: 'https://github.com/advisories/GHSA-low-0000-0000' })
      ),
      {}
    );

    expect(blocking).toEqual([]);
    expect(allowed).toEqual([]);
  });

  test('a clean report passes', () => {
    expect(evaluateAudit({ vulnerabilities: {} }, {}).blocking).toEqual([]);
  });

  test('a report with no vulnerabilities key at all does not crash the gate', () => {
    // npm has changed this shape before. Throwing here would fail the build for
    // the wrong reason; silently passing is what `loadReport` refuses to do.
    expect(evaluateAudit({}, {}).blocking).toEqual([]);
  });

  test('the exit code is 1 when anything blocks, 0 when nothing does', () => {
    const out = { log: vi.fn(), error: vi.fn() };

    expect(reportAudit(evaluateAudit(report(advisory()), {}), {}, out)).toBe(1);
    expect(reportAudit(evaluateAudit({ vulnerabilities: {} }, {}), {}, out)).toBe(0);
  });

  test('a blocked advisory is named, with its package and vulnerable range', () => {
    // The whole point of failing is telling somebody what to fix.
    const out = { log: vi.fn(), error: vi.fn() };
    reportAudit(evaluateAudit(report(advisory()), {}), {}, out);

    const text = out.error.mock.calls.flat().join('\n');
    expect(text).toContain('GHSA-aaaa-bbbb-cccc');
    expect(text).toContain('some-package');
    expect(text).toContain('<1.2.3');
  });
});

describe('the allowlist', () => {
  const listed = { 'GHSA-aaaa-bbbb-cccc': { why: 'unreachable', noFix: 'none', remove: 'when fixed' } };

  test('a listed high passes instead of blocking', () => {
    const { blocking, allowed } = evaluateAudit(report(advisory()), listed);

    expect(blocking).toEqual([]);
    expect(ids(allowed)).toEqual(['GHSA-aaaa-bbbb-cccc']);
  });

  test('listing one advisory does not stop the others blocking', () => {
    // The failure this exists to prevent: dropping the threshold to `critical`
    // to survive one finding, and silently ceasing to guard every other high.
    const { blocking, allowed } = evaluateAudit(
      report(
        advisory(),
        advisory({
          name: 'other-package',
          url: 'https://github.com/advisories/GHSA-dddd-eeee-ffff',
        })
      ),
      listed
    );

    expect(ids(allowed)).toEqual(['GHSA-aaaa-bbbb-cccc']);
    expect(ids(blocking)).toEqual(['GHSA-dddd-eeee-ffff']);
  });

  test('an entry that matched nothing is reported stale — but never fails the build', () => {
    // A greener audit must not turn the build red. The nudge is a message.
    const out = { log: vi.fn(), error: vi.fn() };
    const verdict = evaluateAudit({ vulnerabilities: {} }, listed);

    expect(verdict.stale).toEqual(['GHSA-aaaa-bbbb-cccc']);
    expect(reportAudit(verdict, listed, out)).toBe(0);
    expect(out.log.mock.calls.flat().join('\n')).toContain('stale');
  });

  test('an entry whose advisory dropped below high is stale, not silently kept', () => {
    // Severity is checked before the allowlist, so an entry that no longer
    // holds back anything gets flagged for deletion rather than outliving its
    // own reason unnoticed.
    const verdict = evaluateAudit(report(advisory({ severity: 'moderate' })), listed);

    expect(verdict.allowed).toEqual([]);
    expect(verdict.stale).toEqual(['GHSA-aaaa-bbbb-cccc']);
  });

  test('an allowed advisory prints its reason and its exit condition', () => {
    // An entry is a debt. If the build never restates why it exists and what
    // would let it go, it becomes permanent by inattention.
    const out = { log: vi.fn(), error: vi.fn() };
    reportAudit(evaluateAudit(report(advisory()), listed), listed, out);

    const text = out.log.mock.calls.flat().join('\n');
    expect(text).toContain('unreachable');
    expect(text).toContain('when fixed');
  });

  test('every real entry justifies itself on both counts', () => {
    // The documented bar: no published fix AND unreachable from this app, plus
    // what would let it be deleted. A bare `'GHSA-x': {}` added to make a red
    // build go away is caught here.
    for (const [id, entry] of Object.entries(ALLOWED)) {
      expect(entry.why, `${id} must say why it is unreachable`).toBeTruthy();
      expect(entry.noFix, `${id} must say why there is no fix`).toBeTruthy();
      expect(entry.remove, `${id} must say what would let it be deleted`).toBeTruthy();
      expect(entry.why.length, `${id}: "why" must be an argument, not a word`).toBeGreaterThan(40);
    }
  });
});

describe('reading the report', () => {
  test('one advisory reaching us through several packages is one finding', () => {
    const shared = advisory();
    const parsed = {
      vulnerabilities: {
        'pkg-a': { via: [shared] },
        'pkg-b': { via: [shared] },
        'pkg-c': { via: ['pkg-a'] }, // a re-export, not an advisory
      },
    };

    expect(ids(evaluateAudit(parsed, {}).blocking)).toEqual(['GHSA-aaaa-bbbb-cccc']);
  });

  test('a string `via` is a re-export and carries no advisory of its own', () => {
    const parsed = { vulnerabilities: { 'pkg-a': { via: ['some-other-package'] } } };

    expect(evaluateAudit(parsed, {}).blocking).toEqual([]);
  });

  test('an advisory with no url falls back to its numeric source id', () => {
    const { blocking } = evaluateAudit(report(advisory({ url: undefined })), {});

    expect(ids(blocking)).toEqual(['1234567']);
  });

  test('npm audit exiting non-zero with findings is normal, not a failure', () => {
    // It exits 1 whenever it finds anything, so the exit code is not the signal.
    const err = Object.assign(new Error('exit 1'), {
      stdout: JSON.stringify(report(advisory())),
    });
    const run = vi.fn(() => {
      throw err;
    });

    expect(ids(evaluateAudit(loadReport(run), {}).blocking)).toEqual(['GHSA-aaaa-bbbb-cccc']);
  });

  test('npm audit failing to run at all is fatal, never treated as "clean"', () => {
    // The dangerous silent pass: a scanner that couldn't run must not look the
    // same as a scanner that found nothing.
    const run = vi.fn(() => {
      throw new Error('npm not found');
    });

    expect(() => loadReport(run)).toThrow('npm not found');
  });

  test('main() answers 1 rather than 0 when the audit cannot be run', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(process, 'argv', 'get').mockReturnValue(['node', '/nowhere/audit-gate.mjs']);
    // `loadReport`'s default runner is the real execFileSync; point npm at a
    // command that cannot exist so the failure path runs without a network call.
    const original = process.env.PATH;
    process.env.PATH = '/nonexistent';
    try {
      expect(main()).toBe(1);
    } finally {
      process.env.PATH = original;
      spy.mockRestore();
    }
  });
});

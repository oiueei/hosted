/**
 * The CI dependency gate: `npm audit`, minus a written allowlist.
 *
 * `npm audit --audit-level=high` is all-or-nothing — it cannot accept a single
 * advisory, so one unfixable finding forces the choice between a red pipeline
 * forever and dropping the threshold to `critical`, which would silently stop
 * guarding every other high. This keeps the high/critical threshold and refuses
 * exactly the advisories listed below, each with a reason and an exit condition.
 *
 * An allowlist entry is a debt, not a dismissal. Add one only when the advisory
 * has no published fix AND the vulnerable code path cannot be reached from this
 * app, write down how you know both, and delete it the moment a fix ships.
 * Anything else — including a high with a fix we haven't applied yet — must fail.
 *
 * **Structure**: the decision is `evaluateAudit()`, a pure function over a parsed
 * `npm audit --json` report, and everything below it is I/O — running npm,
 * printing, exiting. That split is what lets `audit-gate.test.js` exercise the
 * gate itself: a gate nobody tests is a gate that can quietly stop guarding, and
 * the failure mode is invisible (a green build that checked nothing).
 */

import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

// Empty, and worth keeping that way. The one entry this list ever held —
// GHSA-qwww-vcr4-c8h2, the react-router RSC-mode CSRF bypass — was accepted
// because its fix (react-router 8.3.0) was unpublished at the time. 8.3.0 has
// since shipped, so the debt was paid the way an allowlist entry is meant to be:
// by taking the upgrade (react-router-dom 7.18.2 -> react-router 8.3.0; v8
// consolidated the two packages, so there is no react-router-dom 8.x) and
// deleting the entry, not by re-justifying it.
export const ALLOWED = {};

export const BLOCKING = new Set(['high', 'critical']);

/**
 * Split a parsed `npm audit --json` report into what fails the build and what
 * doesn't. Pure — no npm, no printing, no exit.
 *
 * Returns `{ blocking, allowed, stale }`, where `stale` names allowlist entries
 * that matched nothing this run.
 */
export function evaluateAudit(report, allowlist = ALLOWED) {
  const blocking = [];
  const allowed = [];
  const seen = new Set();

  for (const vuln of Object.values(report?.vulnerabilities ?? {})) {
    for (const via of vuln?.via ?? []) {
      // A string `via` is a re-export of another package's finding, not an
      // advisory of its own — the advisory objects carry the id and severity.
      if (typeof via !== 'object' || via === null) continue;
      const id = via.url?.split('/').pop() ?? String(via.source);
      // The same advisory reaches us through every package that depends on the
      // vulnerable one; it is one debt, not five.
      if (seen.has(id)) continue;
      seen.add(id);
      // Severity first, deliberately: an allowlist entry for something that is
      // no longer high/critical has stopped doing any work, and reporting it as
      // stale is how it gets deleted instead of quietly outliving its reason.
      if (!BLOCKING.has(via.severity)) continue;
      (allowlist[id] ? allowed : blocking).push({ id, via });
    }
  }

  const stale = Object.keys(allowlist).filter((id) => !allowed.some((e) => e.id === id));
  return { blocking, allowed, stale };
}

/** Print the verdict and return the process exit code. */
export function reportAudit({ blocking, allowed, stale }, allowlist = ALLOWED, out = console) {
  for (const { id, via } of allowed) {
    out.log(`allowed  ${via.severity.padEnd(8)} ${id}  ${via.title}`);
    out.log(`         reason: ${allowlist[id].why}`);
    out.log(`         remove: ${allowlist[id].remove}`);
  }

  // An allowlist entry that no longer matches anything is stale: the advisory
  // was fixed, re-scoped or withdrawn. Say so loudly, but don't fail the build
  // over housekeeping — a green audit must not turn red because it got greener.
  for (const id of stale) {
    out.log(`stale    allowlist entry ${id} matched nothing — delete it from audit-gate.mjs.`);
  }

  for (const { id, via } of blocking) {
    out.error(`BLOCKING ${via.severity.padEnd(8)} ${id}  ${via.title}`);
    out.error(`         package: ${via.name}  vulnerable: ${via.range}`);
  }

  if (blocking.length) {
    out.error(
      `\naudit-gate: ${blocking.length} unaccepted high/critical ` +
        `${blocking.length === 1 ? 'advisory' : 'advisories'}. ` +
        'Fix them, or add an allowlist entry that justifies the exception.'
    );
    return 1;
  }

  out.log(
    `\naudit-gate: no unaccepted high/critical advisories ` +
      `(${allowed.length} allowed, see the reasons above).`
  );
  return 0;
}

/**
 * Run `npm audit --json` and parse it.
 *
 * `npm audit` exits non-zero whenever it finds anything, so the exit code is not
 * the signal here — the parsed report is. Only a crash with no JSON at all is
 * fatal, and it must be: a gate that treats "couldn't run the scanner" as "no
 * findings" is worse than no gate.
 */
export function loadReport(run = execFileSync) {
  try {
    return JSON.parse(
      run('npm', ['audit', '--json'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] })
    );
  } catch (err) {
    if (!err.stdout) throw err;
    return JSON.parse(err.stdout);
  }
}

export function main() {
  let report;
  try {
    report = loadReport();
  } catch (err) {
    console.error('audit-gate: could not run `npm audit`.');
    console.error(err.message);
    return 1;
  }
  return reportAudit(evaluateAudit(report), ALLOWED);
}

// Only shell out when run as a script — importing this module (the tests do)
// must not fire a real `npm audit`.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exit(main());
}

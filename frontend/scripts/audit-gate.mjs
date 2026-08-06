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
 */

import { execFileSync } from 'node:child_process';

const ALLOWED = {
  'GHSA-qwww-vcr4-c8h2': {
    package: 'react-router',
    why:
      'RSC Mode CSRF bypass. OIUEEI runs no RSC and no React Router server: ' +
      'no @react-router/* framework package is installed, App.jsx mounts a ' +
      'client-side <BrowserRouter>, and the build is static files served by ' +
      'WhiteNoise. There is no server route handler for an action to reach.',
    noFix:
      'Fixed in react-router 8.3.0, which is unpublished — 7.18.2 is the ' +
      'latest release. npm can only suggest downgrading to 7.11.0, which ' +
      'reintroduces the four advisories 7.18.2 fixes, including the ' +
      'open redirect in <Link>/useNavigate (CVE-2025-68470 bypass).',
    remove: 'When react-router 8.3.0 ships and the app is upgraded to it.',
  },
};

const BLOCKING = new Set(['high', 'critical']);

// `npm audit` exits non-zero whenever it finds anything, so the exit code is not
// the signal here — the parsed report is. Only a crash (no JSON at all) is fatal.
let report;
try {
  report = JSON.parse(
    execFileSync('npm', ['audit', '--json'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] })
  );
} catch (err) {
  if (!err.stdout) {
    console.error('audit-gate: could not run `npm audit`.');
    console.error(err.message);
    process.exit(1);
  }
  report = JSON.parse(err.stdout);
}

const blocking = [];
const allowed = [];
const seen = new Set();

for (const vuln of Object.values(report.vulnerabilities ?? {})) {
  for (const via of vuln.via ?? []) {
    // A string `via` is a re-export of another package's finding, not an
    // advisory of its own — the advisory objects carry the id and severity.
    if (typeof via !== 'object') continue;
    const id = via.url?.split('/').pop() ?? String(via.source);
    if (seen.has(id)) continue;
    seen.add(id);
    if (!BLOCKING.has(via.severity)) continue;
    (ALLOWED[id] ? allowed : blocking).push({ id, via });
  }
}

for (const { id, via } of allowed) {
  console.log(`allowed  ${via.severity.padEnd(8)} ${id}  ${via.title}`);
  console.log(`         reason: ${ALLOWED[id].why}`);
  console.log(`         remove: ${ALLOWED[id].remove}`);
}

// An allowlist entry that no longer matches anything is stale: the advisory was
// fixed, re-scoped or withdrawn. Say so loudly, but don't fail the build over
// housekeeping — a green audit must not turn red because it got greener.
for (const id of Object.keys(ALLOWED)) {
  if (!allowed.some((entry) => entry.id === id)) {
    console.log(`stale    allowlist entry ${id} matched nothing — delete it from audit-gate.mjs.`);
  }
}

for (const { id, via } of blocking) {
  console.error(`BLOCKING ${via.severity.padEnd(8)} ${id}  ${via.title}`);
  console.error(`         package: ${via.name}  vulnerable: ${via.range}`);
}

if (blocking.length) {
  console.error(
    `\naudit-gate: ${blocking.length} unaccepted high/critical ` +
      `${blocking.length === 1 ? 'advisory' : 'advisories'}. ` +
      'Fix them, or add an allowlist entry that justifies the exception.'
  );
  process.exit(1);
}

console.log(
  `\naudit-gate: no unaccepted high/critical advisories ` +
    `(${allowed.length} allowed, see the reasons above).`
);

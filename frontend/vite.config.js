import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === 'production' ? '/static/' : '/',
  build: {
    // vendor-hds is ~614 kB raw but only ~159 kB gzipped (under our 200 kB-gz
    // bar) — it's the irreducible hds-react library, shared and long-cached.
    // Raising the limit keeps the build green; the per-language i18n locales are
    // now code-split (see src/i18n/index.js), so the remaining win (HDS v6
    // tree-shaking) is tracked separately.
    //
    // The number is a tripwire, not a budget: it sits just above the current
    // chunk so the next HDS minor that grows it materially says so out loud.
    // Raise it deliberately, after checking the gzipped figure — that is the
    // one that governs the 4G mid-range Android target in DESIGN §7. Bumped
    // 600 → 650 on the 6.0.4 → 6.0.5 upgrade (585 → 614 kB raw).
    chunkSizeWarningLimit: 650,
    rollupOptions: {
      output: {
        // Split the rarely-changing vendor libraries from app code so a page
        // edit doesn't bust the (large, cacheable) React/HDS chunks. Pages are
        // already route-split via React.lazy in App.jsx.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (/[\\/]react(-dom)?[\\/]|[\\/]scheduler[\\/]/.test(id)) return 'vendor-react';
          if (id.includes('hds-react') || id.includes('hds-core')) return 'vendor-hds';
          return undefined;
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    css: false,
    // The jest-axe smoke tests on the heaviest form pages take ~4-6 s on a shared
    // CI runner once V8 coverage instrumentation is on (the suite runs 2× slower
    // there than locally) — the 5 s vitest default made them flake. Passing tests
    // don't wait, so the higher ceiling costs nothing.
    testTimeout: 20000,
    coverage: {
      provider: 'v8',
      reporter: ['text-summary', 'html'],
      all: true,
      include: ['src/**/*.{js,jsx}'],
      exclude: [
        'src/main.jsx',
        'src/test/**',
        'src/**/*.test.{js,jsx}',
        'src/stubs/**',
        // `src/i18n/locales/**` is data, not logic — three JSON catalogues whose
        // parity is pinned by `i18nParity.test.js`. `src/i18n/index.js` itself is
        // measured: it stopped being pure configuration when the deployment
        // bundles and the lazy-locale map landed there, and while the whole
        // directory was excluded a real bug in it (a deployment's copy
        // suppressing its own language chunk) was invisible to both the suite
        // and the ratchet.
        'src/i18n/locales/**',
      ],
      // Ratchet floor: set ~2-3 points below the suite's current coverage so it
      // guards against regression without blocking. Raise it as coverage grows.
      // Bumped after the 2026-08 pre-release **testing** round (OwnerBookings,
      // DigestMute, the four irreversible confirms, the guest-list
      // recommendations, the collection digest switch, AddThing +
      // EditCollection) lifted coverage to ~84.2 / 75.3 / 75.9 / 87.7.
      //
      // Raised again at the close of that round, once the Phase B work (the
      // shared-things pager, the inbox dismiss, the collection hero) took the
      // suite to 84.9 / 77.0 / 77.2 / 88.3: branches and functions had drifted
      // to ~4 points of slack, which is wider than this band is meant to be.
      //
      // Raised a third time at the close of the 2026-08 pre-release **testing**
      // round, which took the suite to 85.6 / 77.9 / 78.4 / 88.8 (the i18n
      // bootstrap, the thing-type edit door, the signed-in join). Functions had
      // drifted to ~4.4 points of slack and branches to ~3.9 — the same widening
      // that triggered the last raise. All four are back inside the band.
      //
      // Raised a fourth time after the 2026-08-21 round on the four files that
      // were sitting under the ratchet — VerifyPage (the proposal decisions, the
      // magic-link landing, the stall timeout), the collection broadcast and the
      // ways a collection fails to load, the share menu's delivery half, and the
      // two thing-form controls that carry logic. The suite reads 87.6 / 79.9 /
      // 79.7 / 90.7, so every metric had drifted to 3.7-4.9 points of slack.
      //
      // The floor is not the goal — it only catches a drop. New code still owes
      // tests that name a behaviour; a change that lands under this line means
      // the code needs covering, never that the line needs lowering.
      thresholds: {
        statements: 85,
        branches: 78,
        functions: 77,
        lines: 88,
      },
    },
  },
  resolve: {
    alias: {
      'react': path.resolve(__dirname, 'node_modules/react'),
      'react-dom': path.resolve(__dirname, 'node_modules/react-dom'),
      'postcss': path.resolve(__dirname, 'src/stubs/postcss.js'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
    fs: {
      allow: [
        path.resolve(__dirname, '..'),
      ],
    },
  },
}))

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { render, screen } from '@testing-library/react';
import { describe, test, expect, beforeEach } from 'vitest';
import CancelReservationDialog from '../components/CancelReservationDialog';
import ThemedDialog from '../components/ThemedDialog';

// The line along the top of an HDS Dialog is HDS's blue unless the dialog is
// handed `--accent-line-color`. It takes the viewer's primary theeeme colour.

const THEEEME = { color_01: 'tram', color_02: 'engel-medium-light', color_03: 'summer' };

// HDS turns a `theme` into a generated class (`custom-theme-N`) on the dialog's
// container and inserts its rule into a stylesheet (the CSSOM, not an inline style).
const accentLine = () => {
  const dialog = screen.getByRole('dialog');
  const holder = dialog.closest('[class*="dialogContainer"]') || dialog;
  const generated = [...holder.classList].filter((name) => name.startsWith('custom-theme'));
  for (const sheet of document.styleSheets) {
    for (const rule of sheet.cssRules) {
      if (generated.some((name) => rule.selectorText?.includes(`.${name}`))) {
        const value = rule.style.getPropertyValue('--accent-line-color');
        if (value) return value.trim();
      }
    }
  }
  return undefined;
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('theeemeColors', JSON.stringify(THEEEME));
});

describe('dialogs carry the theeeme colour', () => {
  test('a dialog takes color_01 of the stored theeeme', () => {
    render(
      <ThemedDialog id="d" aria-labelledby="t" isOpen close={() => {}} closeButtonLabelText="Close">
        <ThemedDialog.Header id="t" title="Sure?" />
        <ThemedDialog.Content>Body</ThemedDialog.Content>
      </ThemedDialog>
    );
    expect(accentLine()).toBe('var(--color-tram)');
  });

  test('the reservation-cancel dialog does too', () => {
    render(
      <CancelReservationDialog
        row={{ _code: 'R1', _thingHeadline: 'Lathe', _when: '01/01/2027' }}
        body="Cancel it?"
        confirmLabel="Cancel reservation"
        onConfirm={() => {}}
        onClose={() => {}}
      />
    );
    expect(accentLine()).toBe('var(--color-tram)');
  });

  test('every Dialog in the app goes through ThemedDialog', () => {
    // ShareCollectionMenu (two), OwnerBookingsPage and ManageInvitesPage open only
    // after a flow; what they share is that none imports HDS's Dialog itself.
    const files = [];
    const walk = (dir) => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) walk(path);
        else if (/\.jsx?$/.test(name) && !/\.test\./.test(name)) files.push(path);
      }
    };
    walk('src');
    const direct = files.filter((f) => {
      if (f.endsWith('ThemedDialog.jsx')) return false;
      const src = readFileSync(f, 'utf8');
      return [...src.matchAll(/import\s*\{([^}]*)\}\s*from\s*'hds-react'/g)].some((m) =>
        /\bDialog\b/.test(m[1])
      );
    });
    expect(direct).toEqual([]);
  });
});

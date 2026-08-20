import { render, screen, fireEvent } from '@testing-library/react';
import { vi, describe, test, expect } from 'vitest';

import CollectionModeField from './CollectionModeField';

/**
 * The collection-mode group's own contract — and, more to the point, **the
 * accessible wiring it now gets from HDS instead of by hand**.
 *
 * The block this replaced built its own `<fieldset>` and `<legend>`. Those are
 * what tell a screen-reader user that two radios are one question, and what
 * attach the question's text to them; they were visible in the JSX, so a change
 * that broke them would have been visible in review too. They now come from
 * `SelectionGroup`, which means an HDS upgrade can take them away silently — the
 * exact risk the project's HDS-version policy says the frontend suite has to
 * cover.
 *
 * The rest is the props contract two pages depend on. Nothing here mounts a page:
 * `collectionForm.test.jsx` and `EditCollectionPage.test.jsx` already drive the
 * radios through the real forms, which is what proves the wiring works in place.
 */

const MODES = [
  { value: 'PROPRIETARY', label: 'Just mine', description: 'Only you add things.' },
  { value: 'COMMUNITY', label: 'Shared', description: 'Members add their own things.' },
];

function renderField(overrides = {}) {
  const onChange = vi.fn();
  const utils = render(
    <CollectionModeField
      idPrefix="create-collection"
      label="Who adds things?"
      options={MODES}
      catalogue={MODES}
      value="PROPRIETARY"
      onChange={onChange}
      {...overrides}
    />
  );
  return { ...utils, onChange };
}

describe('the group is one question, not two loose radios', () => {
  test('the options sit in a group named by the label', () => {
    const { container } = renderField();

    // `<fieldset>` + `<legend>`: the semantics HDS supplies now. A radio that
    // announces "Shared" with no idea which question it answers is the
    // regression this catches.
    const group = container.querySelector('fieldset');
    expect(group).not.toBeNull();
    expect(group.querySelector('legend')).toHaveTextContent('Who adds things?');

    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(2);
    radios.forEach((radio) => expect(group.contains(radio)).toBe(true));
  });

  test('each option carries its own description, wired to its own radio', () => {
    renderField();

    MODES.forEach((mode) => {
      const radio = screen.getByRole('radio', { name: mode.label });
      const describedBy = radio.getAttribute('aria-describedby');
      expect(describedBy).toBeTruthy();
      // The description a screen reader reads for this option must be *this*
      // option's — an id collision here reads the wrong explanation aloud.
      expect(document.getElementById(describedBy)).toHaveTextContent(mode.description);
    });
  });

  test('the radios share one name, so picking one clears the other', () => {
    renderField();

    const names = screen.getAllByRole('radio').map((radio) => radio.getAttribute('name'));
    expect(new Set(names).size).toBe(1);
    expect(names[0]).toBe('create-collection-mode');
  });
});

describe('the props contract the two forms rely on', () => {
  test('the current value is the checked one', () => {
    renderField({ value: 'COMMUNITY' });

    expect(screen.getByRole('radio', { name: 'Shared' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Just mine' })).not.toBeChecked();
  });

  test('picking an option reports its value, not an event', () => {
    // The pages pass `handleModeChange`, which takes a mode string.
    const { onChange } = renderField();

    fireEvent.click(screen.getByRole('radio', { name: 'Shared' }));

    expect(onChange).toHaveBeenCalledWith('COMMUNITY');
  });

  test('a narrowed deployment renders only the options it was given', () => {
    // Withheld modes are dropped by the caller, never disabled here: an
    // unchoosable radio is noise, and ApprovalNotice is what names the absence.
    renderField({ options: [MODES[0]], catalogue: MODES });

    expect(screen.getAllByRole('radio')).toHaveLength(1);
    expect(screen.queryByRole('radio', { name: 'Shared' })).toBeNull();
  });

  test('the ids follow the prefix, so two forms can render it on one page', () => {
    const { container } = renderField({ idPrefix: 'edit-collection' });

    expect(container.querySelector('#edit-collection-mode-proprietary')).not.toBeNull();
    expect(container.querySelector('#create-collection-mode-proprietary')).toBeNull();
  });
});

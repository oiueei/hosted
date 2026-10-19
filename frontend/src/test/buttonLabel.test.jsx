import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { Button } from 'hds-react';
import { describe, test, expect } from 'vitest';
import ButtonLink from '../components/ButtonLink';
import { css, rulesIn, declared } from './cssRules';

/**
 * The label of every button — HDS `Button` and `ButtonLink` — is 16/24 Bold.
 * HDS 6 hashes its class names, so a rule that names `.hds-button` matches
 * nothing and the label stays at HDS's own size. The rule's selector list is read
 * from the stylesheet and put to real HDS elements with `matches`, the way
 * `tableLinkWeight.test.jsx` does for its own rule.
 */
const rule = [...css.matchAll(/([^{}]+)\{([^{}]*font-weight:\s*700\s*!important[^{}]*)\}/g)][0];
const selectors = rule[1].split(',').map((s) => s.trim());
const body = rule[2];

const renderButtons = () => {
  const { container } = render(
    <MemoryRouter>
      <Button>primary</Button>
      <Button variant="secondary" size="small">
        small
      </Button>
      <Button variant="supplementary">supplementary</Button>
      <ButtonLink to="/x">link</ButtonLink>
    </MemoryRouter>
  );
  return [...container.querySelectorAll('a, button')];
};

describe('the label of a button', () => {
  test('is 16px, bold, on a 24px line', () => {
    expect(declared(body, 'font-size')).toBe('var(--fontsize-body-m) !important');
    expect(declared(body, 'font-weight')).toBe('700 !important');
    expect(declared(body, 'line-height')).toBe('24px !important');
  });

  test('the rule matches a real HDS Button and a real ButtonLink', () => {
    const elements = renderButtons();
    expect(elements).toHaveLength(4);
    for (const el of elements) {
      expect(
        selectors.some((s) => el.matches(s)),
        el.className
      ).toBe(true);
    }
  });

  test('it does not match what is not a button', () => {
    const { container } = render(
      <MemoryRouter>
        <a href="/x" className="back-link">
          back
        </a>
        <span className="Button-module_buttonLabel__x">label</span>
        <div className="Linkbox-module_linkbox__x" />
      </MemoryRouter>
    );
    for (const el of container.querySelectorAll('*')) {
      expect(
        selectors.some((s) => el.matches(s)),
        el.className
      ).toBe(false);
    }
  });

  test('the old bare class is gone: it matches nothing HDS paints', () => {
    expect(rulesIn(css, '.hds-button')).toEqual([]);
  });
});

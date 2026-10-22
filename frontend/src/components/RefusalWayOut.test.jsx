import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, test } from 'vitest';
import RefusalWayOut from './RefusalWayOut';
import en from '../i18n/locales/en.json';

const THEEEME = {
  color_01: 'bus',
  color_02: 'white',
  color_03: 'bus-light',
  color_04: 'black',
  color_06: 'white',
};

function renderAt(entry) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <RefusalWayOut />
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('theeemeColors', JSON.stringify(THEEEME));
});

describe('RefusalWayOut: where a refused reader goes next', () => {
  test('with a session it is a secondary button to Home', () => {
    localStorage.setItem('userCode', 'U1');
    renderAt('/collections/COL001');

    const link = screen.getByRole('link', { name: en.common.home });
    expect(link).toHaveAttribute('href', '/');
    expect(link.style.getPropertyValue('--background-color')).toBe('var(--color-white)');
    expect(screen.queryByRole('link', { name: en.login.signIn })).toBeNull();
  });

  test('without one it is a primary Sign in that returns to the page being read', () => {
    renderAt('/collections/COL001/things/THG001?x=1');

    const link = screen.getByRole('link', { name: en.login.signIn });
    expect(link).toHaveAttribute(
      'href',
      '/login?next=' + encodeURIComponent('/collections/COL001/things/THG001?x=1')
    );
    expect(link.style.getPropertyValue('--background-color')).toBe('var(--color-bus)');
    expect(screen.queryByRole('link', { name: en.common.home })).toBeNull();
  });
});

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, test, expect } from 'vitest';
import LoginPage from '../pages/LoginPage';
import MagicLinkJoinPage from '../components/MagicLinkJoinPage';
import JoinToAct from '../components/JoinToAct';

/**
 * The three doors that turn a typed email into a magic link — /login, /share/<token>
 * and /collections/<code>/join — paint their submit button the same way: across the
 * whole width of the column, so on a phone it is the width of the screen and on a
 * desktop the width of the form. /join's alone was as wide as its own text
 * (seen on an iPhone).
 *
 * HDS marks full width with a CSS-modules class whose hash changes between builds,
 * so the test reads the class by its stable part ("fullWidth") rather than writing
 * the hash down, and holds the other two doors to what /login does.
 */
const fullWidthClasses = (button) =>
  [...button.classList].filter((name) => /fullWidth/i.test(name));

function submitButtonOf(element, name) {
  const { unmount } = render(<MemoryRouter>{element}</MemoryRouter>);
  const classes = fullWidthClasses(screen.getByRole('button', { name }));
  unmount();
  return classes;
}

describe('the three email doors paint their submit button at the same width', () => {
  const login = () => submitButtonOf(<LoginPage />, 'Sign in');
  const share = () =>
    submitButtonOf(
      <MagicLinkJoinPage
        ns="share"
        docTitleKey="titles.share"
        titleKey="share.pageTitle"
        descriptionKey="share.pageDescription"
        extraBody={{ share_token: 'TOKEN123' }}
      />,
      'Join'
    );
  const join = () =>
    submitButtonOf(
      <JoinToAct
        collectionCode="PUB001"
        collectionHeadline="Tool Library"
        mode="PROPRIETARY"
        allowedThingTypes={['LEND_THING']}
      />,
      'Send me a magic link'
    );

  test('/login is the reference: its button is full width', () => {
    // Without this the two comparisons below could pass by all three being plain.
    expect(login()).not.toEqual([]);
  });

  test('/share/<token> has the same width as /login', () => {
    expect(share()).toEqual(login());
  });

  test('/join has the same width as /login', () => {
    expect(join()).toEqual(login());
  });
});

import { render, screen } from '@testing-library/react';
import { describe, test, expect, afterEach } from 'vitest';
import { axe, toHaveNoViolations } from 'jest-axe';
import i18n from 'i18next';
import en from '../i18n/locales/en.json';
import DemoNotice from './DemoNotice';

expect.extend(toHaveNoViolations);

// The demo banner is deployment copy, not product: upstream ships no
// `demoNotice.*` strings, so it renders nothing however true `is_onboarding` is.
// A deployment that runs an open door adds them through `deploymentI18n`.
const DEPLOYMENT_STRINGS = {
  demoNotice: {
    title: 'This is a demo',
    body: 'The example collections are shared and reset from time to time.',
    realNote: 'Collections you create yourself are real and stay.',
  },
};

describe('DemoNotice', () => {
  afterEach(() => {
    // The mock i18n is a shared singleton — put it back the way the global
    // setup left it so a later test never sees demoNotice keys it didn't add.
    i18n.removeResourceBundle('en', 'translation');
    i18n.addResourceBundle('en', 'translation', en);
  });

  test('renders nothing when the deployment supplies no demoNotice copy', () => {
    const { container } = render(<DemoNotice />);
    expect(container).toBeEmptyDOMElement();
  });

  test('renders the alert when the deployment supplies the copy', () => {
    i18n.addResourceBundle('en', 'translation', DEPLOYMENT_STRINGS, true, true);

    render(<DemoNotice />);

    expect(screen.getByText('This is a demo')).toBeInTheDocument();
    // Both beats DESIGN_HOSTED §1 wants: what IS demo, and what is not.
    expect(
      screen.getByText('The example collections are shared and reset from time to time.')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Collections you create yourself are real and stay.')
    ).toBeInTheDocument();
  });

  test('the rendered alert has no axe violations', async () => {
    i18n.addResourceBundle('en', 'translation', DEPLOYMENT_STRINGS, true, true);

    const { container } = render(<DemoNotice />);

    expect(await axe(container)).toHaveNoViolations();
  });
});

import { render, screen } from '@testing-library/react';
import { describe, test, expect, afterEach, vi } from 'vitest';

// This file is about what a deployment with no forms of its own hosted elsewhere shows
// — the app's own contact page, `VITE_FEEDBACK_URL`, the server's request address. A
// core test cannot assume what `deployment/` holds (U16, V9, round W §0.5), so the
// `externalForms` a deployment may have are switched off here by stubbing the helper
// that reads them; `externalForms.test.jsx` pins them on, with the module mocked.
vi.mock('../utils/externalForms', () => ({ externalFormUrl: () => null }));

// Service-layer policy, not product (S2): without VITE_FEEDBACK_URL the
// component offers no door at all — the same pattern as `popInPath`/
// `aboutPath` in `src/deployment/`. `import.meta.env.VITE_*` is read once at
// module load, so each test resets the module cache and re-imports it after
// stubbing the env — the only way to exercise both branches in one file.
const URL = 'https://forms.example/deployment-feedback';

async function loadWith(url) {
  vi.stubEnv('VITE_FEEDBACK_URL', url);
  return (await import('./FeedbackLink')).default;
}

describe('FeedbackLink', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  test('upstream (no VITE_FEEDBACK_URL) renders nothing', async () => {
    const FeedbackLink = await loadWith('');

    const { container } = render(<FeedbackLink />);

    expect(container).toBeEmptyDOMElement();
  });

  test('a deployment that sets the env var gets a link named "Ideas and bugs" to it, in a new tab', async () => {
    const FeedbackLink = await loadWith(URL);

    render(<FeedbackLink />);

    const link = screen.getByRole('link', { name: /^Ideas and bugs/ });
    expect(link).toHaveAttribute('href', URL);
    expect(link).toHaveAttribute('target', '_blank');
    expect(link.getAttribute('rel')).toMatch(/noopener/);
  });

  test('the button says only "Ideas and bugs"; the new tab is announced, not printed', async () => {
    // HDS's own `openInNewTab` appends "(Opens in a new tab.)" to the visible
    // text — not the short label asked for — so the announcement lives in the
    // accessible name, which still starts with the words on the button.
    const FeedbackLink = await loadWith(URL);

    render(<FeedbackLink />);

    const link = screen.getByRole('link', { name: /^Ideas and bugs/ });
    expect(link).toHaveTextContent(/^Ideas and bugs$/);
    expect(link).toHaveAccessibleName('Ideas and bugs. Opens in a new tab.');
  });

  test('it is the `<a>` alone — nothing around it, so it can sit in a row of buttons', async () => {
    const FeedbackLink = await loadWith(URL);

    const { container } = render(<FeedbackLink />);

    expect(container.children).toHaveLength(1);
    expect(container.firstElementChild.tagName).toBe('A');
    expect(container.firstElementChild.className).toMatch(/hds-button/);
  });

  test('the caller decides which button it is: `style` reaches the link', async () => {
    const FeedbackLink = await loadWith(URL);

    render(<FeedbackLink style={{ '--background-color': 'rgb(1, 2, 3)' }} />);

    expect(
      screen
        .getByRole('link', { name: /^Ideas and bugs/ })
        .style.getPropertyValue('--background-color')
    ).toBe('rgb(1, 2, 3)');
  });
});

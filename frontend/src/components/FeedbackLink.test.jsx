import { render, screen } from '@testing-library/react';
import { describe, test, expect, afterEach, vi } from 'vitest';

// Service-layer policy, not product (S2): without VITE_FEEDBACK_URL the
// component offers no door at all — the same pattern as `popInPath`/
// `aboutPath` in `src/deployment/`. `import.meta.env.VITE_*` is read once at
// module load, so each test resets the module cache and re-imports it after
// stubbing the env — the only way to exercise both branches in one file.
describe('FeedbackLink', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  test('upstream (no VITE_FEEDBACK_URL) renders nothing', async () => {
    vi.stubEnv('VITE_FEEDBACK_URL', '');
    const { default: FeedbackLink } = await import('./FeedbackLink');

    const { container } = render(<FeedbackLink />);

    expect(container).toBeEmptyDOMElement();
  });

  test('a deployment that sets the env var gets a link pointing at it', async () => {
    vi.stubEnv('VITE_FEEDBACK_URL', 'https://forms.example/deployment-feedback');
    const { default: FeedbackLink } = await import('./FeedbackLink');

    render(<FeedbackLink />);

    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', 'https://forms.example/deployment-feedback');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });
});

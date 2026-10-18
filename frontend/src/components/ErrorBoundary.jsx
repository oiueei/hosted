import { Component } from 'react';
import { Button } from 'hds-react';
import i18n from '../i18n';

/**
 * Top-level error boundary.
 *
 * React 19 unmounts the whole tree on an uncaught render error, so without this
 * a single malformed API payload or render bug would leave a blank white screen
 * with no way out. This catches the throw and renders a recoverable fallback.
 *
 * Kept deliberately self-contained and resilient: it uses the i18n instance
 * directly (class components can't use the useTranslation hook) with English
 * defaultValues, so the fallback still renders even if the failure is
 * translation- or data-related. The layout is inline and the buttons are HDS
 * `Button`s painted with the HDS colour tokens (each with its hex as the fallback
 * of `var()`), so the fallback does not depend on app CSS or on a theeeme.
 */
class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    // Surface for debugging in development only — never print full stacks and
    // component trees into end users' consoles in production. This is where a
    // future error-reporting hook (e.g. Sentry) would receive the error.
    if (import.meta.env.DEV) {
      console.error('Unhandled render error:', error, info);
    }
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    const t = (key, fallback) => i18n.t(key, { defaultValue: fallback });

    const wrap = {
      maxWidth: 480,
      margin: '15vh auto',
      padding: '0 24px',
      textAlign: 'center',
    };
    const row = {
      display: 'flex',
      gap: 12,
      justifyContent: 'center',
      marginTop: 24,
      flexWrap: 'wrap',
    };
    // Black-90 on white: the neutral palette, needing no theeeme (the tree that
    // would have supplied one is the thing that just failed).
    const primary = {
      '--background-color': 'var(--color-black-90, #1a1a1a)',
      '--background-color-hover': 'var(--color-black-80, #333333)',
      '--background-color-focus': 'var(--color-black-90, #1a1a1a)',
      '--border-color': 'var(--color-black-90, #1a1a1a)',
      '--border-color-focus': 'var(--color-black-90, #1a1a1a)',
      '--color': 'var(--color-white, #ffffff)',
      '--color-focus': 'var(--color-white, #ffffff)',
    };
    const secondary = {
      '--background-color': 'var(--color-white, #ffffff)',
      '--background-color-hover': 'var(--color-black-5, #f2f2f2)',
      '--background-color-focus': 'var(--color-white, #ffffff)',
      '--border-color': 'var(--color-black-90, #1a1a1a)',
      '--border-color-focus': 'var(--color-black-90, #1a1a1a)',
      '--color': 'var(--color-black-90, #1a1a1a)',
      '--color-focus': 'var(--color-black-90, #1a1a1a)',
    };

    return (
      <div role="alert" style={wrap}>
        <h1>{t('errorBoundary.title', 'Something went wrong')}</h1>
        <p>
          {t(
            'errorBoundary.body',
            'An unexpected error occurred. Try reloading the page, or go back home.'
          )}
        </p>
        <div style={row}>
          <Button type="button" onClick={() => window.location.reload()} style={primary}>
            {t('errorBoundary.reload', 'Reload page')}
          </Button>
          <Button
            type="button"
            onClick={() => {
              window.location.href = '/';
            }}
            style={secondary}
          >
            {t('errorBoundary.home', 'Go home')}
          </Button>
        </div>
      </div>
    );
  }
}

export default ErrorBoundary;

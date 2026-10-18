import { render, screen, fireEvent } from '@testing-library/react';
import { describe, test, expect, vi, afterEach } from 'vitest';
import ErrorBoundary from '../components/ErrorBoundary';

function Boom() {
  throw new Error('boom');
}

describe('ErrorBoundary', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test('renders children when there is no error', () => {
    render(
      <ErrorBoundary>
        <p>all good</p>
      </ErrorBoundary>
    );
    expect(screen.getByText('all good')).toBeInTheDocument();
  });

  test('renders a recoverable fallback when a child throws', () => {
    // React logs caught errors to console.error — silence the expected noise.
    vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    );

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reload page' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Go home' })).toBeInTheDocument();
  });

  describe('its two buttons', () => {
    const original = window.location;
    afterEach(() => {
      Object.defineProperty(window, 'location', { value: original, configurable: true });
    });

    function renderFallback() {
      vi.spyOn(console, 'error').mockImplementation(() => {});
      const location = { reload: vi.fn(), href: 'http://localhost/page' };
      Object.defineProperty(window, 'location', { value: location, configurable: true });
      render(
        <ErrorBoundary>
          <Boom />
        </ErrorBoundary>
      );
      return location;
    }

    test('are HDS buttons, painted with HDS tokens', () => {
      renderFallback();

      for (const name of ['Reload page', 'Go home']) {
        const button = screen.getByRole('button', { name });
        expect(button.className).toMatch(/Button-module_button/);
        expect(button.getAttribute('style')).toMatch(/var\(--color-black-90/);
      }
    });

    test('Reload page reloads, Go home goes to the root', () => {
      const location = renderFallback();

      fireEvent.click(screen.getByRole('button', { name: 'Reload page' }));
      expect(location.reload).toHaveBeenCalledTimes(1);
      expect(location.href).toBe('http://localhost/page');

      fireEvent.click(screen.getByRole('button', { name: 'Go home' }));
      expect(location.href).toBe('/');
    });
  });
});

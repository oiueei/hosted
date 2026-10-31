import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import ToggleWithHelp from '../components/ToggleWithHelp';
import fs from 'node:fs';

expect.extend(toHaveNoViolations);

describe('ToggleWithHelp', () => {
  it('names the button with the title alone and describes it with a paragraph of its own', () => {
    render(
      <ToggleWithHelp
        id="t"
        label="Public"
        help="Anyone can read it."
        checked
        onChange={() => {}}
      />
    );
    const button = screen.getByRole('button', { name: 'Public' });
    const help = screen.getByText('Anyone can read it.');
    expect(help.tagName).toBe('P');
    expect(help.className).toBe('toggle-help');
    expect(button.getAttribute('aria-describedby')).toBe(help.id);
    expect(button.closest('[class*="toggleButtonContainer"]')).not.toContainElement(help);
  });

  it('paints no paragraph and no description without a help text', () => {
    const { container } = render(
      <ToggleWithHelp id="t" label="Endless" checked={false} onChange={() => {}} />
    );
    expect(screen.getByRole('button', { name: 'Endless' })).not.toHaveAttribute('aria-describedby');
    expect(container.querySelector('.toggle-help')).toBeNull();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <ToggleWithHelp id="t" label="Public" help="Anyone." checked onChange={() => {}} />
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it('is styled by the stylesheet and the old wrapper is gone', () => {
    const css = fs.readFileSync('src/App.css', 'utf8');
    expect(css).not.toContain('toggle-left');
    expect(css).toMatch(/\.toggle-help\s*{[^}]*font-size:\s*var\(--fontsize-body-s\)/);
    expect(css).toMatch(/\.toggle-help\s*{[^}]*color:\s*var\(--color-black-70\)/);
  });
});

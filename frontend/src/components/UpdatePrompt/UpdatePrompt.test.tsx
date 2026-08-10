import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { UpdatePrompt } from './UpdatePrompt';

function renderPrompt(overrides: Partial<Parameters<typeof UpdatePrompt>[0]> = {}) {
  const onSkip = vi.fn();
  const onLater = vi.fn();
  render(
    <UpdatePrompt
      open
      latestVersion="3.2.0"
      currentVersion="3.1.1"
      downloadUrl="https://example.test/win.exe"
      pageUrl="https://example.test/rel"
      onSkip={onSkip}
      onLater={onLater}
      {...overrides}
    />,
  );
  return { onSkip, onLater };
}

describe('UpdatePrompt', () => {
  it('names both versions and offers the three choices', () => {
    renderPrompt();
    expect(screen.getByText(/3\.2\.0 is available/)).toBeInTheDocument();
    expect(screen.getByText(/running 3\.1\.1/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Download' })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Skip this version' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Later' })).toBeInTheDocument();
  });

  it('points Download at the installer asset', () => {
    renderPrompt();
    expect(screen.getByRole('link', { name: 'Download' })).toHaveAttribute(
      'href',
      'https://example.test/win.exe',
    );
  });

  it('falls back to the releases page when the release has no asset', () => {
    renderPrompt({ downloadUrl: null });
    expect(screen.getByRole('link', { name: 'Download' })).toHaveAttribute(
      'href',
      'https://example.test/rel',
    );
  });

  it('wires Skip and Later to their callbacks', async () => {
    const user = userEvent.setup();
    const { onSkip, onLater } = renderPrompt();
    await user.click(screen.getByRole('button', { name: 'Skip this version' }));
    expect(onSkip).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'Later' }));
    expect(onLater).toHaveBeenCalledTimes(1);
  });
});

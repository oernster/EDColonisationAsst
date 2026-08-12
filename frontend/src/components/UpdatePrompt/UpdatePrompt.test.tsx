import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { UpdatePrompt } from './UpdatePrompt';

function renderPrompt(overrides: Partial<Parameters<typeof UpdatePrompt>[0]> = {}) {
  const onClose = vi.fn();
  render(
    <UpdatePrompt
      open
      latestVersion="3.2.0"
      currentVersion="3.1.1"
      downloadUrl="https://example.test/win.exe"
      pageUrl="https://example.test/rel"
      onClose={onClose}
      {...overrides}
    />,
  );
  return { onClose };
}

describe('UpdatePrompt', () => {
  it('names both versions and offers the two choices', () => {
    renderPrompt();
    expect(screen.getByText(/3\.2\.0 is available/)).toBeInTheDocument();
    expect(screen.getByText(/running 3\.1\.1/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Download' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();
  });

  it('offers no skip, because this HUD never prompts unbidden', () => {
    // Skipping silences an automatic check and the only one lives in the
    // tray, which keeps its own skip. A button here would write a
    // preference nothing would ever read.
    renderPrompt();
    expect(
      screen.queryByRole('button', { name: /skip/i }),
    ).not.toBeInTheDocument();
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

  it('closes on Download as well as on Close', async () => {
    const user = userEvent.setup();
    const { onClose } = renderPrompt();
    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('link', { name: 'Download' }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});

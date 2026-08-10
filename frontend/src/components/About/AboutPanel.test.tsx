import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { AboutPanel } from './AboutPanel';
import type { ManualCheckOutcome } from '../../hooks/useUpdateCheck';

function renderPanel(outcome: ManualCheckOutcome | Promise<ManualCheckOutcome>) {
  const onCheckForUpdates = vi.fn().mockReturnValue(Promise.resolve(outcome));
  render(
    <AboutPanel
      appVersion="3.2.0"
      pythonVersion="3.11.0"
      healthError={null}
      onCheckForUpdates={onCheckForUpdates}
    />,
  );
  return { onCheckForUpdates };
}

describe('AboutPanel manual update check', () => {
  it('runs the check when the button is clicked', async () => {
    const user = userEvent.setup();
    const { onCheckForUpdates } = renderPanel('latest');
    await user.click(screen.getByRole('button', { name: 'Check for Updates' }));
    expect(onCheckForUpdates).toHaveBeenCalledTimes(1);
  });

  it('reports up to date', async () => {
    const user = userEvent.setup();
    renderPanel('latest');
    await user.click(screen.getByRole('button', { name: 'Check for Updates' }));
    expect(
      await screen.findByText('You are running the latest version.'),
    ).toBeInTheDocument();
  });

  it('reports an unreachable check', async () => {
    const user = userEvent.setup();
    renderPanel('unreachable');
    await user.click(screen.getByRole('button', { name: 'Check for Updates' }));
    expect(
      await screen.findByText(
        'The update check could not reach GitHub. Please try again later.',
      ),
    ).toBeInTheDocument();
  });

  it('shows no message on an update outcome; the prompt opens upstream', async () => {
    const user = userEvent.setup();
    renderPanel('update');
    await user.click(screen.getByRole('button', { name: 'Check for Updates' }));
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Check for Updates' }),
      ).toBeEnabled(),
    );
    expect(
      screen.queryByText('You are running the latest version.'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/could not reach GitHub/),
    ).not.toBeInTheDocument();
  });

  it('disables the button while a check is in flight and clears a stale message', async () => {
    const user = userEvent.setup();
    let resolveCheck: (outcome: ManualCheckOutcome) => void = () => {};
    const pending = new Promise<ManualCheckOutcome>((resolve) => {
      resolveCheck = resolve;
    });
    const onCheckForUpdates = vi
      .fn<() => Promise<ManualCheckOutcome>>()
      .mockReturnValueOnce(Promise.resolve('latest'))
      .mockReturnValueOnce(pending);
    render(
      <AboutPanel
        appVersion="3.2.0"
        pythonVersion="3.11.0"
        healthError={null}
        onCheckForUpdates={onCheckForUpdates}
      />,
    );

    const button = screen.getByRole('button', { name: 'Check for Updates' });
    await user.click(button);
    expect(
      await screen.findByText('You are running the latest version.'),
    ).toBeInTheDocument();

    await user.click(button);
    expect(button).toBeDisabled();
    expect(
      screen.queryByText('You are running the latest version.'),
    ).not.toBeInTheDocument();

    resolveCheck('unreachable');
    expect(
      await screen.findByText(/could not reach GitHub/),
    ).toBeInTheDocument();
    expect(button).toBeEnabled();
  });
});

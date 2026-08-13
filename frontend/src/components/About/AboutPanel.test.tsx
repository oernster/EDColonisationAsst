import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AboutPanel } from './AboutPanel';

function renderPanel(overrides: Partial<Parameters<typeof AboutPanel>[0]> = {}) {
  render(
    <AboutPanel
      appVersion="3.3.0"
      pythonVersion="3.13.0"
      healthError={null}
      {...overrides}
    />,
  );
}

describe('AboutPanel', () => {
  it('reports the versions the backend gave it', () => {
    renderPanel();
    expect(screen.getByText('Version: 3.3.0')).toBeInTheDocument();
    expect(screen.getByText('Python runtime: 3.13.0')).toBeInTheDocument();
  });

  it('says loading rather than inventing a version it does not have', () => {
    renderPanel({ appVersion: null, pythonVersion: null });
    expect(screen.getByText('Version: Loading...')).toBeInTheDocument();
    expect(screen.getByText('Python runtime: Loading...')).toBeInTheDocument();
  });

  it('shows a health error when the backend reported one', () => {
    renderPanel({ healthError: 'Backend unreachable' });
    expect(screen.getByText('Backend unreachable')).toBeInTheDocument();
  });

  it('offers no update check at all', () => {
    // The guard on the removal rather than a test of absence for its own sake.
    // This HUD is served over the local network and cannot tell whether the
    // device reading it is the machine EDCA is installed on, so any update
    // surface here offers a download to a tablet that cannot install it. The
    // tray owns the check. If this test starts failing, the surface has come
    // back and the tablet problem has come back with it.
    renderPanel();
    expect(
      screen.queryByRole('button', { name: /update/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/latest version/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/GitHub/i)).not.toBeInTheDocument();
  });
});

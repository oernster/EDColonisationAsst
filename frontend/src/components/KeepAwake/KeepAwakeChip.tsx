/**
 * The keep-awake status indicator.
 *
 * Shown on mobile and tablet only: desktop users do not need it and it is
 * visual noise there. The state machine it renders is the one useKeepAwake
 * reports, with one addition of its own: while the preference is on but the
 * hook still reads "off", it shows Starting rather than a misleading Off.
 */

import { Chip, Tooltip } from '@mui/material';

import { isMobileOrTablet } from '../../utils/device';

const LABEL_BASE = 'Keep awake';

export interface KeepAwakeChipProps {
  enabled: boolean;
  status: { state: string; message: string };
  wakeLockPossible: boolean;
  secureContext: boolean;
  onEnableFromUserGesture: () => void;
}

export function KeepAwakeChip({
  enabled,
  status,
  wakeLockPossible,
  secureContext,
  onEnableFromUserGesture,
}: KeepAwakeChipProps) {
  if (!isMobileOrTablet()) return null;

  const tooltip = status.message;

  // Avoid a brief "Off" state while the keep-awake hook is attempting to enable.
  if (enabled && status.state === 'off') {
    return (
      <Tooltip title="Enabling keep-awake…" arrow>
        <Chip size="small" label={`${LABEL_BASE}: Starting`} color="default" variant="outlined" />
      </Tooltip>
    );
  }

  if (status.state === 'active') {
    return (
      <Tooltip title={tooltip} arrow>
        <Chip size="small" label={`${LABEL_BASE}: On`} color="success" variant="filled" />
      </Tooltip>
    );
  }

  if (status.state === 'needs-user-gesture') {
    return (
      <Tooltip title={tooltip} arrow>
        <Chip
          size="small"
          label={`${LABEL_BASE}: Tap to enable`}
          color="warning"
          variant="filled"
          onClick={onEnableFromUserGesture}
        />
      </Tooltip>
    );
  }

  if (enabled && status.state === 'unsupported') {
    const extra =
      wakeLockPossible || secureContext
        ? ''
        : ' (HTTP/LAN often blocks Wake Lock; fallback requires a tap)';
    return (
      <Tooltip title={`${tooltip}${extra}`} arrow>
        <Chip
          size="small"
          label={`${LABEL_BASE}: Unsupported`}
          color="default"
          variant="outlined"
        />
      </Tooltip>
    );
  }

  if (enabled && status.state === 'error') {
    return (
      <Tooltip title={tooltip} arrow>
        <Chip size="small" label={`${LABEL_BASE}: Error`} color="error" variant="filled" />
      </Tooltip>
    );
  }

  return (
    <Tooltip title={enabled ? tooltip : 'Off'} arrow>
      <Chip size="small" label={`${LABEL_BASE}: Off`} color="default" variant="outlined" />
    </Tooltip>
  );
}

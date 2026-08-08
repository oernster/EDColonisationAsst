import { useEffect, useState } from 'react';
import { Chip } from '@mui/material';

import type { CarrierTransit } from '../../types/fleetCarriers';
import { transitLabel } from './carrierTransit';

/**
 * How often the countdown is redrawn.
 *
 * The backend long-poll is what keeps the transit state itself honest; this
 * timer exists only so the seconds tick down between those updates.
 */
const TICK_INTERVAL_MS = 1000;

interface CarrierTransitChipProps {
  transit?: CarrierTransit | null;
  /** Bounds the chip in the carrier rows, which are narrower than the header. */
  maxWidth?: number;
}

/**
 * The chip that says where a carrier is heading, and when it leaves.
 *
 * Renders nothing at all for a parked carrier: the location chip beside it
 * already says where it is, and an empty "not going anywhere" chip on every
 * row would be noise. The ticking clock is local state rather than a prop so
 * that both places this appears keep their own countdown without the parent
 * re-rendering once a second.
 */
export const CarrierTransitChip = ({ transit, maxWidth }: CarrierTransitChipProps) => {
  const [now, setNow] = useState(() => new Date());

  const scheduled = transit?.state === 'in_transit';

  useEffect(() => {
    if (!scheduled) {
      return;
    }

    const id = window.setInterval(() => setNow(new Date()), TICK_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [scheduled]);

  const label = transitLabel(transit, now);
  if (!label) {
    return null;
  }

  return (
    <Chip
      label={label}
      color="warning"
      size="small"
      variant="outlined"
      sx={maxWidth ? { maxWidth } : undefined}
    />
  );
};

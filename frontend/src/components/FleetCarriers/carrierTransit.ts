/**
 * Wording for a carrier's movement state.
 *
 * Kept apart from the component that shows it so the phrasing can be tested
 * against a fixed clock rather than whatever time the test happened to run.
 *
 * One point of accuracy drives all of this. A booked jump does not move the
 * carrier: it stays exactly where it is until its departure time, then makes
 * the jump in about a minute. So the label counts down to the departure, and
 * only once that moment has passed does it claim the carrier is arriving.
 */

import type { CarrierTransit } from '../../types/fleetCarriers';

const MS_PER_SECOND = 1000;
const SECONDS_PER_MINUTE = 60;
const MINUTES_PER_HOUR = 60;

/** Two digits, so 9 minutes past reads as 09 rather than 9. */
const clockPart = (value: number): string => String(value).padStart(2, '0');

/**
 * The departure moment as a local wall clock time.
 *
 * Deliberately local rather than the journal's UTC: the countdown beside it
 * is what carries the precision, and a local time is the one a commander can
 * compare against their own clock.
 */
export const formatDepartureClock = (departure: Date): string =>
  `${clockPart(departure.getHours())}:${clockPart(departure.getMinutes())}`;

/** A rounded-down gap, in the largest two units that apply. */
export const formatCountdown = (millis: number): string => {
  const totalSeconds = Math.max(0, Math.floor(millis / MS_PER_SECOND));
  const seconds = totalSeconds % SECONDS_PER_MINUTE;
  const totalMinutes = Math.floor(totalSeconds / SECONDS_PER_MINUTE);
  const minutes = totalMinutes % MINUTES_PER_HOUR;
  const hours = Math.floor(totalMinutes / MINUTES_PER_HOUR);

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
};

/**
 * What to put on the transit chip, or null when there is nothing to say.
 *
 * Null covers both a carrier with no jump history and one sitting parked:
 * neither warrants a chip, because the location chip beside it already says
 * where the carrier is.
 */
export const transitLabel = (
  transit: CarrierTransit | null | undefined,
  now: Date,
): string | null => {
  if (!transit || transit.state !== 'in_transit') {
    return null;
  }

  const destination = transit.destination_system;
  if (!destination) {
    return null;
  }

  if (!transit.departure_time) {
    return `Jumping to ${destination}`;
  }

  const departure = new Date(transit.departure_time);
  if (Number.isNaN(departure.getTime())) {
    return `Jumping to ${destination}`;
  }

  const remaining = departure.getTime() - now.getTime();
  if (remaining <= 0) {
    // Departure has come and gone without an arrival in the journals yet,
    // which is the one window where the carrier really is between systems.
    return `Arriving at ${destination}`;
  }

  return (
    `Jumping to ${destination} at ${formatDepartureClock(departure)} ` +
    `(in ${formatCountdown(remaining)})`
  );
};

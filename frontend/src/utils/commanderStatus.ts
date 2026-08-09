/**
 * Turning the journal-derived commander status into header copy.
 *
 * Lives here rather than in App so the phrasing is testable as functions and
 * the station-type mapping has one home.
 */

import { CurrentSystem } from '../types/colonisation';

// Journal StationType values that mean a surface installation rather than an
// orbital station. Anything unrecognised reads as a station, which is the
// honest default for types this map has never seen.
const PLANETARY_TYPES = new Set(['CraterOutpost', 'CraterPort', 'OnFootSettlement']);

export function stationKind(stationType: string | null | undefined): string {
  if (stationType === 'FleetCarrier') return 'carrier';
  if (stationType && PLANETARY_TYPES.has(stationType)) return 'planetary base';
  return 'station';
}

export function formatCredits(balance: number): string {
  return `${balance.toLocaleString('en-GB')} CR`;
}

export function describeLocation(status: CurrentSystem): string | null {
  const system = status.current_system;
  if (status.is_docked && status.station_name) {
    const where = system ? ` in ${system}` : '';
    return `Docked at ${status.station_name} ${stationKind(status.station_type)}${where}`;
  }
  return system ? `In ${system}` : null;
}

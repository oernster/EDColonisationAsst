import { describe, expect, it } from 'vitest';

import { describeLocation, formatCredits, stationKind } from './commanderStatus';

describe('stationKind', () => {
  it('maps a fleet carrier to carrier', () => {
    expect(stationKind('FleetCarrier')).toBe('carrier');
  });

  it('maps surface types to planetary base', () => {
    expect(stationKind('CraterOutpost')).toBe('planetary base');
    expect(stationKind('CraterPort')).toBe('planetary base');
    expect(stationKind('OnFootSettlement')).toBe('planetary base');
  });

  it('defaults everything else, including unknowns, to station', () => {
    expect(stationKind('Coriolis')).toBe('station');
    expect(stationKind('SomethingNew')).toBe('station');
    expect(stationKind(null)).toBe('station');
    expect(stationKind(undefined)).toBe('station');
  });
});

describe('formatCredits', () => {
  it('groups thousands and appends CR', () => {
    expect(formatCredits(1234567890)).toBe('1,234,567,890 CR');
    expect(formatCredits(0)).toBe('0 CR');
  });
});

describe('describeLocation', () => {
  it('describes a docked commander with station kind and system', () => {
    expect(
      describeLocation({
        current_system: 'Shinrarta Dezhra',
        is_docked: true,
        station_name: 'Jameson Memorial',
        station_type: 'Coriolis',
      }),
    ).toBe('Docked at Jameson Memorial station in Shinrarta Dezhra');
  });

  it('describes a docked commander at a carrier', () => {
    expect(
      describeLocation({
        current_system: 'Lupus Dark Region BQ-Y d66',
        is_docked: true,
        station_name: 'X7J-BQG',
        station_type: 'FleetCarrier',
      }),
    ).toBe('Docked at X7J-BQG carrier in Lupus Dark Region BQ-Y d66');
  });

  it('omits the system clause when the system is unknown', () => {
    expect(
      describeLocation({
        current_system: null,
        is_docked: true,
        station_name: 'Somewhere',
        station_type: 'Outpost',
      }),
    ).toBe('Docked at Somewhere station');
  });

  it('falls back to the system alone when not docked', () => {
    expect(
      describeLocation({ current_system: 'Sol', is_docked: false }),
    ).toBe('In Sol');
  });

  it('returns null when nothing is known', () => {
    expect(describeLocation({ current_system: null })).toBeNull();
  });
});

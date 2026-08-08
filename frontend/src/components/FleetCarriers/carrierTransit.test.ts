import { describe, expect, it } from 'vitest';

import type { CarrierTransit } from '../../types/fleetCarriers';
import { formatCountdown, formatDepartureClock, transitLabel } from './carrierTransit';

const DEPARTURE = '2026-06-16T20:09:10Z';

const booked = (overrides: Partial<CarrierTransit> = {}): CarrierTransit => ({
  state: 'in_transit',
  destination_system: 'Fong Wang',
  destination_body: 'Fong Wang 4',
  departure_time: DEPARTURE,
  ...overrides,
});

/** The label quotes a local wall clock, so the expectation must be local too. */
const localClock = (iso: string): string => {
  const moment = new Date(iso);
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${pad(moment.getHours())}:${pad(moment.getMinutes())}`;
};

describe('formatCountdown', () => {
  it('gives seconds alone under a minute', () => {
    expect(formatCountdown(45_000)).toBe('45s');
  });

  it('gives minutes and seconds under an hour', () => {
    expect(formatCountdown(12 * 60_000 + 30_000)).toBe('12m 30s');
  });

  it('drops to hours and minutes once past an hour', () => {
    expect(formatCountdown(65 * 60_000)).toBe('1h 5m');
  });

  it('never counts below zero', () => {
    expect(formatCountdown(-5_000)).toBe('0s');
  });
});

describe('formatDepartureClock', () => {
  it('pads a single-digit minute', () => {
    const moment = new Date('2026-06-16T20:09:10Z');
    expect(formatDepartureClock(moment)).toBe(localClock('2026-06-16T20:09:10Z'));
    expect(formatDepartureClock(moment)).toMatch(/^\d{2}:\d{2}$/);
  });
});

describe('transitLabel', () => {
  const now = new Date('2026-06-16T19:56:40Z');

  it('says nothing when there is no transit information', () => {
    expect(transitLabel(null, now)).toBeNull();
    expect(transitLabel(undefined, now)).toBeNull();
  });

  it('says nothing for a parked carrier, because the location chip covers it', () => {
    expect(transitLabel({ state: 'parked' }, now)).toBeNull();
  });

  it('says nothing when the destination is missing', () => {
    expect(transitLabel(booked({ destination_system: null }), now)).toBeNull();
  });

  it('counts down to the departure rather than claiming the carrier has moved', () => {
    // A booked jump leaves the carrier exactly where it is until it departs.
    expect(transitLabel(booked(), now)).toBe(
      `Jumping to Fong Wang at ${localClock(DEPARTURE)} (in 12m 30s)`,
    );
  });

  it('switches to arriving once the departure has passed', () => {
    const afterDeparture = new Date('2026-06-16T20:09:40Z');
    expect(transitLabel(booked(), afterDeparture)).toBe('Arriving at Fong Wang');
  });

  it('treats the exact departure moment as departed', () => {
    expect(transitLabel(booked(), new Date(DEPARTURE))).toBe('Arriving at Fong Wang');
  });

  it('drops the countdown when the journal carried no departure time', () => {
    expect(transitLabel(booked({ departure_time: null }), now)).toBe(
      'Jumping to Fong Wang',
    );
  });

  it('drops the countdown when the departure time is unreadable', () => {
    expect(transitLabel(booked({ departure_time: 'not a time' }), now)).toBe(
      'Jumping to Fong Wang',
    );
  });
});

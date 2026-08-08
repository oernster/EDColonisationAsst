/**
 * Characterisation tests for the Fleet carriers tab.
 *
 * The panel was one 752-line file and is now six, so what these assert is that
 * every surface that moved still renders the same words: the not-docked copy,
 * the docked header and its chips, the service list (filtered, relabelled and
 * sorted by display name), the market columns and the cargo totals.
 *
 * The store's actions are replaced with no-ops rather than mocked at the API
 * layer, because these are about what the components draw from a given state,
 * not about how that state is fetched.
 */

import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { FleetCarriersPanel } from './FleetCarriersPanel'
import { useCarrierStore } from '../../stores/carrierStore'
import {
  CarrierIdentity,
  CarrierState,
  MyCarriersResponse,
} from '../../types/fleetCarriers'

const OWN_CARRIER: CarrierIdentity = {
  carrier_id: 3700569600,
  market_id: 128000001,
  name: 'MIDNIGHT ELOQUENCE',
  callsign: 'X7J-BQG',
  role: 'own',
  docking_access: 'squadron',
  last_seen_system: 'Lupus Dark Region BQ-Y d66',
  // Deliberately unsorted, carrying two services the panel hides.
  services: ['voucherredemption', 'flightcontroller', 'autodock', 'stationmenu'],
}

const SQUADRON_CARRIER: CarrierIdentity = {
  carrier_id: 3700000001,
  name: 'SQUADRON HAULER',
  callsign: 'ABC-123',
  role: 'squadron',
  last_seen_system: 'Sol',
  services: [],
}

const CARRIER_STATE: CarrierState = {
  identity: OWN_CARRIER,
  cargo: [
    {
      commodity_name: 'titanium',
      commodity_name_localised: 'Titanium',
      stock: 240,
      capacity: 500,
      reserved: 12,
    },
  ],
  space_usage: {
    total_capacity: 25000,
    crew: 1000,
    module_packs: 500,
    cargo: 240,
  },
  total_cargo_tonnage: 240,
  total_capacity_tonnage: 25000,
  free_space_tonnage: 23260,
  buy_orders: [
    {
      order_type: 'buy',
      commodity_name: 'titanium',
      commodity_name_localised: 'Titanium',
      price: 4446,
      original_amount: 100,
      remaining_amount: 60,
    },
  ],
  sell_orders: [
    {
      order_type: 'sell',
      commodity_name: 'gold',
      commodity_name_localised: 'Gold',
      price: 50000,
      original_amount: 20,
      remaining_amount: 20,
    },
  ],
  snapshot_time: '2026-01-01T00:00:00Z',
}

const NO_CARRIERS: MyCarriersResponse = {
  own_carriers: [],
  squadron_carriers: [],
}

/** Put the store in a known state with its actions inert. */
const setStore = (overrides: Partial<ReturnType<typeof useCarrierStore.getState>>) => {
  useCarrierStore.setState({
    currentCarrierInfo: null,
    currentCarrierState: null,
    lastKnownCarrierState: null,
    currentCarrierLoading: false,
    currentCarrierError: null,
    myCarriers: NO_CARRIERS,
    myCarriersLoading: false,
    myCarriersError: null,
    carrierViewTab: 'market',
    loadCurrentCarrier: vi.fn().mockResolvedValue(undefined),
    refreshCurrentCarrier: vi.fn().mockResolvedValue(undefined),
    forceRefreshCurrentCarrier: vi.fn().mockResolvedValue(undefined),
    loadMyCarriers: vi.fn().mockResolvedValue(undefined),
    setCarrierViewTab: vi.fn(),
    clearCarrierError: vi.fn(),
    ...overrides,
  })
}

describe('FleetCarriersPanel', () => {
  beforeEach(() => {
    setStore({})
  })

  it('says you are not docked when there is no docked carrier', () => {
    render(<FleetCarriersPanel />)

    expect(screen.getByText(/not currently docked at a fleet carrier/i)).toBeTruthy()
    expect(screen.getByText(/No own or squadron carriers were found/i)).toBeTruthy()
  })

  it('shows the docked carrier name, callsign and chips', () => {
    setStore({
      currentCarrierInfo: { docked_at_carrier: true, carrier: OWN_CARRIER },
      currentCarrierState: CARRIER_STATE,
    })

    render(<FleetCarriersPanel />)

    expect(screen.getByText('MIDNIGHT ELOQUENCE')).toBeTruthy()
    expect(screen.getByText('(X7J-BQG)')).toBeTruthy()
    expect(screen.getByText('Access: Squadron only')).toBeTruthy()
    // A carrier is parked in a system or in transit; it is never "docked",
    // and "last seen" understated what the journal actually knows.
    expect(
      screen.getByText('Current star system: Lupus Dark Region BQ-Y d66'),
    ).toBeTruthy()
    expect(screen.getByText('Cargo: 240 t')).toBeTruthy()
  })

  it('hides the noise services and labels the rest, sorted by display name', () => {
    setStore({
      currentCarrierInfo: { docked_at_carrier: true, carrier: OWN_CARRIER },
      currentCarrierState: CARRIER_STATE,
    })

    render(<FleetCarriersPanel />)

    // flightcontroller and stationmenu are hidden; the other two are relabelled.
    expect(screen.getByText('Auto dock')).toBeTruthy()
    expect(screen.getByText('Redemption office')).toBeTruthy()
    expect(screen.queryByText(/flight ?controller/i)).toBeNull()
    expect(screen.queryByText(/station ?menu/i)).toBeNull()

    // Sorted by display name, not by the raw name and not in journal order:
    // the fixture lists voucherredemption before autodock on purpose, so a
    // panel that skipped the sort would fail here.
    const rendered = document.body.textContent ?? ''
    expect(rendered.indexOf('Auto dock')).toBeLessThan(rendered.indexOf('Redemption office'))
  })

  it('lists buy and sell orders on the market tab', () => {
    setStore({
      currentCarrierInfo: { docked_at_carrier: true, carrier: OWN_CARRIER },
      currentCarrierState: CARRIER_STATE,
      carrierViewTab: 'market',
    })

    render(<FleetCarriersPanel />)

    expect(screen.getByText('Buy orders')).toBeTruthy()
    expect(screen.getByText('Sell orders')).toBeTruthy()
    expect(screen.getByText('Titanium')).toBeTruthy()
    expect(screen.getByText('Gold')).toBeTruthy()
    expect(screen.getByText('4,446 CR/t')).toBeTruthy()
    expect(screen.getByText(/60 \/\s*100 t/)).toBeTruthy()
  })

  it('computes free space after buy orders on the cargo tab', () => {
    setStore({
      currentCarrierInfo: { docked_at_carrier: true, carrier: OWN_CARRIER },
      currentCarrierState: { ...CARRIER_STATE, cargo: [] },
      carrierViewTab: 'cargo',
    })

    render(<FleetCarriersPanel />)

    // 25000 total - 1000 crew - 500 module packs - 240 cargo - 60 outstanding.
    expect(screen.getByText('Free after all buy orders: 23,200 t')).toBeTruthy()
    expect(screen.getByText('Outstanding buy orders: 60 t')).toBeTruthy()
    expect(screen.getByText('Capacity: 25,000 t')).toBeTruthy()
  })

  it('shows the per-commodity hold when a market export has been read', () => {
    setStore({
      currentCarrierInfo: { docked_at_carrier: true, carrier: OWN_CARRIER },
      currentCarrierState: CARRIER_STATE,
      carrierViewTab: 'cargo',
    })

    render(<FleetCarriersPanel />)

    expect(screen.getByText(/Carrier hold, heaviest first/i)).toBeTruthy()
    expect(screen.getByText('(Buy order)')).toBeTruthy()
    expect(screen.getByText('12 t reserved')).toBeTruthy()
  })

  it('says when the hold is read from the carrier market and still agrees with it', () => {
    setStore({
      currentCarrierInfo: { docked_at_carrier: true, carrier: OWN_CARRIER },
      currentCarrierState: {
        ...CARRIER_STATE,
        cargo_snapshot_time: '2026-06-21T17:51:30Z',
        cargo_unaccounted_tonnage: 0,
      },
      carrierViewTab: 'cargo',
    })

    render(<FleetCarriersPanel />)

    expect(screen.getByText(/Hold read from the carrier market at/i)).toBeTruthy()
    expect(screen.getByText('Matches carrier total')).toBeTruthy()
  })

  it('reports tonnage the journal cannot account for rather than hiding it', () => {
    setStore({
      currentCarrierInfo: { docked_at_carrier: true, carrier: OWN_CARRIER },
      currentCarrierState: {
        ...CARRIER_STATE,
        cargo_snapshot_time: '2026-06-21T17:51:30Z',
        cargo_unaccounted_tonnage: 446,
      },
      carrierViewTab: 'cargo',
    })

    render(<FleetCarriersPanel />)

    expect(screen.getByText('Carrier reports 446 t more')).toBeTruthy()
  })

  it('claims nothing about agreement when there is no carrier total to check', () => {
    setStore({
      currentCarrierInfo: { docked_at_carrier: true, carrier: OWN_CARRIER },
      currentCarrierState: {
        ...CARRIER_STATE,
        cargo_snapshot_time: '2026-06-21T17:51:30Z',
        cargo_unaccounted_tonnage: null,
      },
      carrierViewTab: 'cargo',
    })

    render(<FleetCarriersPanel />)

    expect(screen.queryByText('Matches carrier total')).toBeNull()
    expect(screen.queryByText(/Carrier reports/)).toBeNull()
  })

  it('reports a hold that has shrunk since the export just as plainly', () => {
    setStore({
      currentCarrierInfo: { docked_at_carrier: true, carrier: OWN_CARRIER },
      currentCarrierState: {
        ...CARRIER_STATE,
        cargo_snapshot_time: '2026-06-21T17:51:30Z',
        cargo_unaccounted_tonnage: -80,
      },
      carrierViewTab: 'cargo',
    })

    render(<FleetCarriersPanel />)

    expect(screen.getByText('Carrier reports 80 t less')).toBeTruthy()
  })

  it('tells you how to get a breakdown when no export has been read', () => {
    setStore({
      currentCarrierInfo: { docked_at_carrier: true, carrier: OWN_CARRIER },
      currentCarrierState: { ...CARRIER_STATE, cargo: [] },
      carrierViewTab: 'cargo',
    })

    render(<FleetCarriersPanel />)

    expect(screen.getByText(/open its commodity market once/i)).toBeTruthy()
  })

  it('marks the carrier you are standing on in the known-carriers list', () => {
    setStore({
      currentCarrierInfo: { docked_at_carrier: true, carrier: OWN_CARRIER },
      currentCarrierState: CARRIER_STATE,
      myCarriers: {
        own_carriers: [OWN_CARRIER],
        squadron_carriers: [SQUADRON_CARRIER],
      },
    })

    render(<FleetCarriersPanel />)

    // The chip describes where the COMMANDER is, not the carrier.
    expect(screen.getByText('You are docked here')).toBeTruthy()
    expect(screen.getByText('Squadron carriers')).toBeTruthy()
    // A carrier with no services at all shows its callsign and nothing more.
    expect(screen.getByText('ABC-123')).toBeTruthy()
  })

  it('surfaces a load failure as an alert', () => {
    setStore({ currentCarrierError: 'Failed to load current carrier information' })

    render(<FleetCarriersPanel />)

    const alert = screen.getByRole('alert')
    expect(within(alert).getByText(/Failed to load current carrier information/)).toBeTruthy()
  })
})

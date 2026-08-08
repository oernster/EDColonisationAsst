/**
 * Tests for the carrier status view.
 *
 * The rule under test throughout is that the view never invents a reading.
 * CarrierStats has changed shape across game updates, so anything the journal
 * did not carry is left out rather than drawn as a zero: a fuel gauge reading
 * empty because the event was quiet would be worse than no gauge at all.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CarrierStatusSection } from './CarrierStatusSection'
import { CarrierStatus } from '../../types/fleetCarriers'

const FULL_STATUS: CarrierStatus = {
  fuel_level: 1000,
  jump_range_current: 500,
  jump_range_max: 500,
  pending_decommission: false,
  finance: {
    carrier_balance: 3401638229,
    reserve_balance: 31632848,
    available_balance: 3280907361,
    reserve_percent: 1,
    tax_rate_rearm: 15,
    tax_rate_refuel: 15,
    tax_rate_repair: 15,
  },
  crew: [
    { role: 'BlackMarket', activated: false },
    { role: 'Captain', activated: true, enabled: true, name: 'Swara Phillips' },
    { role: 'Refuel', activated: true, enabled: true, name: 'Sara Carey' },
    { role: 'Repair', activated: true, enabled: false, name: 'Everett Sampson' },
  ],
}

describe('CarrierStatusSection', () => {
  it('says so plainly when no CarrierStats has been seen', () => {
    render(<CarrierStatusSection status={null} />)

    expect(screen.getByText(/No CarrierStats event has been seen/i)).toBeTruthy()
  })

  it('shows the fuel and both jump ranges', () => {
    render(<CarrierStatusSection status={FULL_STATUS} />)

    expect(screen.getByText('Fuel: 1,000 t')).toBeTruthy()
    expect(screen.getByText('Jump range: 500.0 ly')).toBeTruthy()
    expect(screen.getByText('Maximum range: 500.0 ly')).toBeTruthy()
  })

  it('shows the balances and the tax charged to visitors', () => {
    render(<CarrierStatusSection status={FULL_STATUS} />)

    expect(screen.getByText('Balance: 3,401,638,229 CR')).toBeTruthy()
    expect(screen.getByText('Available: 3,280,907,361 CR')).toBeTruthy()
    expect(screen.getByText('Reserve rate: 1%')).toBeTruthy()
    expect(screen.getByText('Refuel tax: 15%')).toBeTruthy()
  })

  it('names the captain separately from the services', () => {
    render(<CarrierStatusSection status={FULL_STATUS} />)

    expect(screen.getByText('Captain: Swara Phillips')).toBeTruthy()
  })

  it('distinguishes a hired service that has been switched off', () => {
    render(<CarrierStatusSection status={FULL_STATUS} />)

    expect(screen.getByText('Refuel (Sara Carey)')).toBeTruthy()
    expect(screen.getByText('Repair (Everett Sampson), switched off')).toBeTruthy()
  })

  it('lists the positions never hired, with their names made readable', () => {
    render(<CarrierStatusSection status={FULL_STATUS} />)

    // CamelCase in the journal, sentence case on screen.
    expect(screen.getByText(/Not hired:\s*Black market/i)).toBeTruthy()
  })

  it('shouts about a pending decommission', () => {
    render(
      <CarrierStatusSection status={{ ...FULL_STATUS, pending_decommission: true }} />,
    )

    expect(screen.getByText(/scheduled for decommissioning/i)).toBeTruthy()
  })

  it('stays quiet about a decommission that is not pending', () => {
    render(<CarrierStatusSection status={FULL_STATUS} />)

    expect(screen.queryByText(/scheduled for decommissioning/i)).toBeNull()
  })

  it('omits readings the journal did not carry rather than showing zero', () => {
    render(
      <CarrierStatusSection
        status={{ pending_decommission: false, crew: [] }}
      />,
    )

    expect(screen.queryByText(/^Fuel:/)).toBeNull()
    expect(screen.queryByText(/^Balance:/)).toBeNull()
    expect(screen.queryByText(/^Jump range:/)).toBeNull()
  })

  it('shows what a partial finance block has and nothing more', () => {
    render(
      <CarrierStatusSection
        status={{
          pending_decommission: false,
          crew: [],
          finance: { carrier_balance: 42 },
        }}
      />,
    )

    expect(screen.getByText('Balance: 42 CR')).toBeTruthy()
    expect(screen.queryByText(/^Available:/)).toBeNull()
  })
})

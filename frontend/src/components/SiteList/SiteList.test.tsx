/**
 * Characterisation tests for the system view.
 *
 * SiteList.tsx was one 598-line file holding two pure derivations and four
 * components. What these assert is that every surface that moved still behaves
 * the same: the aggregation arithmetic, the completed-station rule, the three
 * empty states, which sites each view mode shows and what a site card says.
 *
 * The arithmetic is tested directly rather than through a render, which is the
 * point of having pulled it out into siteAggregation.ts.
 *
 * One test in App.test.tsx already covered the per-site progress label. It is
 * left where it is and still passes; this file does not duplicate it.
 */

import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { SiteList } from './SiteList'
import {
  aggregateCommodities,
  displayedProgress,
  isStationCompleted,
} from './siteAggregation'
import { useColonisationStore } from '../../stores/colonisationStore'
import {
  Commodity,
  CommodityStatus,
  ConstructionSite,
  SystemColonisationData,
} from '../../types/colonisation'

const commodity = (overrides: Partial<Commodity> = {}): Commodity => ({
  name: 'steel',
  name_localised: 'Steel',
  required_amount: 100,
  provided_amount: 40,
  payment: 1000,
  remaining_amount: 60,
  progress_percentage: 40,
  status: CommodityStatus.IN_PROGRESS,
  ...overrides,
})

const site = (overrides: Partial<ConstructionSite> = {}): ConstructionSite => ({
  market_id: 1,
  station_name: 'Alpha Depot',
  station_type: 'Orbital Construction Site',
  system_name: 'Sol',
  system_address: 10,
  construction_progress: 40,
  construction_complete: false,
  construction_failed: false,
  commodities: [commodity()],
  last_updated: '2026-01-01T00:00:00.000Z',
  is_complete: false,
  total_commodities_needed: 1,
  commodities_progress_percentage: 40,
  last_source: 'journal',
  ...overrides,
})

/** A site that satisfies every clause of the completed rule. */
const completedSite = (overrides: Partial<ConstructionSite> = {}): ConstructionSite =>
  site({
    market_id: 2,
    station_name: 'Beta Depot',
    construction_complete: true,
    is_complete: true,
    commodities: [
      commodity({
        provided_amount: 100,
        remaining_amount: 0,
        progress_percentage: 100,
        status: CommodityStatus.COMPLETED,
      }),
    ],
    ...overrides,
  })

const systemWith = (sites: ConstructionSite[]): SystemColonisationData => ({
  system_name: 'Sol',
  construction_sites: sites,
  total_sites: sites.length,
  completed_sites: sites.filter((s) => s.construction_complete).length,
  in_progress_sites: sites.filter((s) => !s.construction_complete).length,
  completion_percentage: 50,
})

const setSystem = (systemData: SystemColonisationData | null) => {
  useColonisationStore.setState({
    currentSystem: systemData ? systemData.system_name : null,
    systemData,
    loading: false,
    error: null,
  })
}

describe('siteAggregation', () => {
  it('sums a commodity across every site that wants it', () => {
    const [aggregate] = aggregateCommodities([
      site({ market_id: 1, station_name: 'Alpha Depot' }),
      site({ market_id: 2, station_name: 'Beta Depot' }),
    ])

    expect(aggregate.total_required).toBe(200)
    expect(aggregate.total_provided).toBe(80)
    expect(aggregate.total_remaining).toBe(120)
    expect(aggregate.progress_percentage).toBe(40)
    expect(aggregate.average_payment).toBe(1000)
  })

  it('lists only the sites that still want some of it', () => {
    const [aggregate] = aggregateCommodities([
      site({ market_id: 1, station_name: 'Still Wants It' }),
      site({
        market_id: 2,
        station_name: 'Already Fed',
        commodities: [commodity({ provided_amount: 100, remaining_amount: 0 })],
      }),
    ])

    expect(aggregate.sites_requiring).toEqual(['Still Wants It'])
  })

  it('orders the list by what is most outstanding', () => {
    const aggregates = aggregateCommodities([
      site({
        commodities: [
          commodity({ name: 'small', remaining_amount: 1, required_amount: 10 }),
          commodity({ name: 'large', remaining_amount: 900, required_amount: 900 }),
        ],
      }),
    ])

    expect(aggregates.map((a) => a.commodity_name)).toEqual(['large', 'small'])
  })

  it('calls a commodity with nothing required fully complete', () => {
    const [aggregate] = aggregateCommodities([
      site({
        commodities: [commodity({ required_amount: 0, provided_amount: 0 })],
      }),
    ])

    expect(aggregate.progress_percentage).toBe(100)
    expect(aggregate.total_remaining).toBe(0)
  })

  it('requires all three clauses before a station counts as completed', () => {
    expect(isStationCompleted(completedSite())).toBe(true)
    expect(isStationCompleted(completedSite({ is_complete: false }))).toBe(false)
    expect(isStationCompleted(completedSite({ construction_complete: false }))).toBe(false)
    // Flagged complete, yet a commodity is still outstanding.
    expect(isStationCompleted(completedSite({ commodities: [commodity()] }))).toBe(false)
  })

  it('clamps the displayed progress and reports a complete site as 100', () => {
    expect(displayedProgress(true, 40)).toBe(100)
    expect(displayedProgress(false, null)).toBeNull()
    expect(displayedProgress(false, 140)).toBe(100)
    expect(displayedProgress(false, -5)).toBe(0)
  })
})

describe('SiteList', () => {
  beforeEach(() => {
    setSystem(systemWith([site()]))
  })

  it('says there are no sites at all when the system is empty', () => {
    setSystem(systemWith([]))
    render(<SiteList viewMode="system" />)

    expect(screen.getByText('No construction sites found in this system')).toBeTruthy()
  })

  it('says there are no in-progress stations when every site is finished', () => {
    setSystem(systemWith([completedSite()]))
    render(<SiteList viewMode="stations" />)

    expect(screen.getByText('No in-progress stations found in this system')).toBeTruthy()
  })

  it('says there are no completed stations when none are finished', () => {
    render(<SiteList viewMode="completed_stations" />)

    expect(screen.getByText('No completed stations found in this system')).toBeTruthy()
  })

  it('shows the summary and the shopping list in the system view', () => {
    render(<SiteList viewMode="system" />)

    expect(screen.getByText('Sol')).toBeTruthy()
    expect(screen.getByText('Total Sites')).toBeTruthy()
    expect(screen.getByText('System Shopping List')).toBeTruthy()
    expect(screen.getByText('Steel')).toBeTruthy()
    expect(screen.getByText(/Need 60 more/)).toBeTruthy()
    expect(screen.getByText('Needed at:')).toBeTruthy()
  })

  it('explains an empty shopping list rather than showing nothing', () => {
    setSystem(systemWith([completedSite()]))
    render(<SiteList viewMode="system" />)

    expect(screen.getByText(/No commodity requirements are currently available/)).toBeTruthy()
  })

  it('shows only the unfinished sites in the stations view', () => {
    setSystem(systemWith([site(), completedSite()]))
    render(<SiteList viewMode="stations" />)

    const tabs = screen.getAllByRole('tab')
    expect(tabs.map((tab) => tab.textContent)).toEqual(['Alpha Depot'])
    expect(screen.getByTestId('site-progress-label-1').textContent).toContain('40.0%')
  })

  it('shows only the finished sites in the completed view', () => {
    setSystem(systemWith([site(), completedSite()]))
    render(<SiteList viewMode="completed_stations" />)

    const tabs = screen.getAllByRole('tab')
    expect(tabs.map((tab) => tab.textContent)).toEqual(['Beta Depot'])
    expect(screen.getByText(/All commodities delivered/)).toBeTruthy()
    expect(screen.getByText('COMPLETE')).toBeTruthy()
  })

  it('awaits requirements rather than showing zero when a site has none', () => {
    setSystem(systemWith([site({ commodities: [] })]))
    render(<SiteList viewMode="stations" />)

    expect(screen.getByText('Awaiting requirements')).toBeTruthy()
    expect(screen.queryByTestId('site-progress-label-1')).toBeNull()
  })
})

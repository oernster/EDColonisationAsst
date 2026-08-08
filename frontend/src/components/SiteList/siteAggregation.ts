/**
 * The arithmetic behind the system view, kept away from the components.
 *
 * Three derivations, all pure and all worth testing without rendering
 * anything:
 *
 * - `aggregateCommodities` rolls every site's requirements into one shopping
 *   list for the system.
 * - `isStationCompleted` decides which sites count as finished, which is what
 *   the in-progress and completed tabs filter on.
 * - `siteDeliveryProgress` works out how far one site has got, from commodity
 *   totals rather than from the journal's own progress field.
 */

import {
  CommodityAggregate,
  CommodityStatus,
  ConstructionSite,
} from '../../types/colonisation'

const FULLY_COMPLETE_PERCENTAGE = 100

/**
 * Roll the commodities of every site into one list for the whole system.
 *
 * Ordered by how much is still outstanding, so the commodity the commander
 * most needs to go and buy is at the top.
 */
export const aggregateCommodities = (
  sites: ConstructionSite[],
): CommodityAggregate[] => {
  const commodityMap: {
    [name: string]: {
      name: string
      name_localised: string
      total_required: number
      total_provided: number
      sites: Set<string>
      payments: number[]
    }
  } = {}

  sites.forEach((site) => {
    site.commodities.forEach((commodity) => {
      const key = commodity.name

      if (!commodityMap[key]) {
        commodityMap[key] = {
          name: commodity.name,
          name_localised: commodity.name_localised,
          total_required: 0,
          total_provided: 0,
          sites: new Set<string>(),
          payments: [],
        }
      }

      const entry = commodityMap[key]

      entry.total_required += commodity.required_amount
      entry.total_provided += commodity.provided_amount

      // Only sites that still want some of it are worth listing under
      // "Needed at".
      if (commodity.remaining_amount > 0) {
        entry.sites.add(site.station_name)
      }

      entry.payments.push(commodity.payment)
    })
  })

  const aggregates: CommodityAggregate[] = Object.values(commodityMap).map(
    (data) => {
      const average_payment =
        data.payments.length > 0
          ? data.payments.reduce((sum, value) => sum + value, 0) /
            data.payments.length
          : 0

      const total_remaining = Math.max(
        0,
        data.total_required - data.total_provided,
      )

      const progress_percentage =
        data.total_required === 0
          ? FULLY_COMPLETE_PERCENTAGE
          : (data.total_provided / data.total_required) *
            FULLY_COMPLETE_PERCENTAGE

      return {
        commodity_name: data.name,
        commodity_name_localised: data.name_localised,
        total_required: data.total_required,
        total_provided: data.total_provided,
        sites_requiring: Array.from(data.sites),
        average_payment,
        total_remaining,
        progress_percentage,
      }
    },
  )

  aggregates.sort((a, b) => b.total_remaining - a.total_remaining)

  return aggregates
}

/**
 * Whether a station counts as finished.
 *
 * NOTE: user-requested rule: station is completed iff ALL of these are true.
 * Backend currently sets is_complete := construction_complete; we still honor
 * both fields.
 */
export const isStationCompleted = (site: ConstructionSite): boolean => {
  const hasAllCommoditiesDelivered =
    site.commodities.length === 0 ||
    site.commodities.every(
      (c) => c.remaining_amount === 0 || c.status === CommodityStatus.COMPLETED,
    )

  return (
    Boolean(site.construction_complete) &&
    Boolean(site.is_complete) &&
    hasAllCommoditiesDelivered
  )
}

export interface SiteDeliveryProgress {
  totalRequired: number
  totalProvided: number
  /** Null when the site has advertised no requirements to measure against. */
  deliveryProgressPercentage: number | null
  hasRequirements: boolean
}

/**
 * How far one site has got, measured by commodity deliveries.
 *
 * Deliberately NOT the journal's own ConstructionProgress field, which can
 * sit unchanged for long periods while deliveries are happening. A site that
 * has advertised no requirements yet has no meaningful percentage, which is
 * the null case rather than a zero.
 */
export const siteDeliveryProgress = (
  site: ConstructionSite,
): SiteDeliveryProgress => {
  const commodities = site.commodities ?? []
  const totalRequired = commodities.reduce(
    (sum, c) => sum + (c.required_amount ?? 0),
    0,
  )
  const totalProvided = commodities.reduce(
    (sum, c) => sum + (c.provided_amount ?? 0),
    0,
  )

  const hasRequirements = commodities.length > 0 && totalRequired > 0

  return {
    totalRequired,
    totalProvided,
    deliveryProgressPercentage: hasRequirements
      ? (totalProvided / totalRequired) * FULLY_COMPLETE_PERCENTAGE
      : null,
    hasRequirements,
  }
}

/**
 * The percentage to paint, clamped to the bar's range.
 *
 * A completed site reads 100 whatever its commodity totals say, because the
 * two can disagree when the game reports completion before the last delivery
 * lands.
 */
export const displayedProgress = (
  isComplete: boolean,
  deliveryProgressPercentage: number | null,
): number | null => {
  if (isComplete) {
    return FULLY_COMPLETE_PERCENTAGE
  }
  if (deliveryProgressPercentage === null) {
    return null
  }
  return Math.max(
    0,
    Math.min(FULLY_COMPLETE_PERCENTAGE, deliveryProgressPercentage),
  )
}

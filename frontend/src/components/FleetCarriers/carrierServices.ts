/**
 * Turning raw journal service names into something worth showing.
 *
 * The journal writes carrier services in several shapes for the same thing:
 * bare words, snake_case, and occasionally the `$Name;` wrapper. It also lists
 * services that are on every carrier or specific to the commander, which say
 * nothing about the carrier being looked at.
 *
 * Two places need this: the header of the carrier you are docked at, and each
 * row of the known-carriers list. They had a copy each of the same filter and
 * sort, which is what `visibleServicesSorted` now is.
 */

/**
 * Normalise a raw journal/service name into a compact key we can use for
 * matching overrides and filters.
 */
export const normalizeServiceKey = (service: string): string =>
  service.toLowerCase().replace(/\s+/g, '').replace(/[_-]/g, '')

/**
 * Services that are either commander-specific or effectively always-present
 * and therefore not useful to show in the UI.
 */
export const HIDDEN_SERVICE_KEYS = new Set<string>([
  'flightcontroller',
  'socialspace',
  'engineer',
  'stationmenu',
  'stationoperations',
])

/**
 * Human-friendly label overrides for specific carrier services.
 *
 * These keep each logical service as a single item, but add spaces to make
 * them readable.
 */
const SERVICE_LABEL_OVERRIDES: Record<string, string> = {
  autodock: 'Auto dock',
  carrierfuel: 'Carrier fuel',
  carriermanagement: 'Carrier management',
  crewlounge: 'Crew lounge',
  exploration: 'Cartographics',
  pioneersupplies: 'Pioneer supplies',
  vistagenomics: 'Vista genomics',
  voucherredemption: 'Redemption office',
}

export const formatServiceName = (service: string) => {
  const key = normalizeServiceKey(service)
  const override = SERVICE_LABEL_OVERRIDES[key]
  if (override) {
    return override
  }

  let name = service

  // Strip common prefixes/suffixes if present (defensive; journals vary).
  if (name.startsWith('$') && name.endsWith(';')) {
    name = name.slice(1, -1)
  }

  name = name.replace(/_/g, ' ')
  if (!name) {
    return service
  }

  // Crew roles arrive as CamelCase (BlackMarket, VoucherRedemption) where
  // station services arrive lowercase, so splitting on an interior capital
  // reads the first correctly and leaves the second untouched.
  name = name.replace(/([a-z])([A-Z])/g, '$1 $2')

  const [first, ...rest] = name.split(' ')
  return [
    first.charAt(0).toUpperCase() + first.slice(1),
    ...rest.map((word) => word.toLowerCase()),
  ].join(' ')
}

/**
 * The services worth showing, ordered the way they will read.
 *
 * Sorted by display name rather than by raw name, because that is the order
 * the eye will check. Returns the raw names so callers can still key on them;
 * `formatServiceName` turns each into its label.
 */
export const visibleServicesSorted = (services: string[]): string[] =>
  services
    .filter((service) => !HIDDEN_SERVICE_KEYS.has(normalizeServiceKey(service)))
    .sort((a, b) => formatServiceName(a).localeCompare(formatServiceName(b)))

export const formatDockingAccess = (access: string) => {
  const normalized = access.toLowerCase()
  switch (normalized) {
    case 'owner':
      return 'Owner only'
    case 'squadron':
      return 'Squadron only'
    case 'friends':
      return 'Friends & squadron'
    case 'all':
      return 'All pilots'
    default:
      return access.charAt(0).toUpperCase() + access.slice(1)
  }
}

/**
 * TypeScript types for Fleet carrier data.
 *
 * These mirror the backend models in backend/src/models/carriers.py and
 * backend/src/models/api_models.py so that the Fleet carriers UI can be
 * strongly typed.
 */

export type CarrierRole = 'own' | 'squadron' | 'other';

/**
 * Whether a carrier is holding station or has a jump booked.
 *
 * A carrier is never docked anywhere: it sits in a star system, or it has a
 * jump scheduled and is on its way out. A cancelled jump is not a third
 * state, it simply returns the carrier to parked.
 */
export type CarrierTransitState = 'parked' | 'in_transit';

export interface CarrierTransit {
  state: CarrierTransitState;
  /** Star system being jumped to. Null while parked. */
  destination_system?: string | null;
  /** Body the carrier will hold at, when the journal named one. */
  destination_body?: string | null;
  /**
   * When the carrier leaves, which is what the countdown runs against. The
   * carrier stays put in its current system until this moment.
   */
  departure_time?: string | null;
}

export interface CarrierIdentity {
  carrier_id: number | null;
  market_id?: number | null;
  name: string;
  callsign?: string | null;
  role: CarrierRole;
  /**
   * Docking access policy as reported by the journal (e.g. "owner", "squadron",
   * "friends", "all"). This is surfaced in the UI for additional context.
   */
  docking_access?: string | null;
  last_seen_system?: string | null;
  last_seen_timestamp?: string | null;
  /**
   * Raw list of carrier services (e.g. cartographics, outfitting, shipyard)
   * derived from CarrierStats.Services or StationServices on the Docked event.
   */
  services?: string[] | null;
  /**
   * Whether the carrier is holding station or has a jump booked, derived from
   * its jump and location events. Null when the journals carry no jump
   * history for it at all, which is not the same as knowing it is parked.
   */
  transit?: CarrierTransit | null;
}

export interface CarrierCargoItem {
  commodity_name: string;
  commodity_name_localised: string;
  stock: number;
  reserved?: number;
  capacity?: number;
}

export type CarrierOrderType = 'buy' | 'sell';

export interface CarrierOrder {
  order_type: CarrierOrderType;
  commodity_name: string;
  commodity_name_localised: string;
  price: number;
  original_amount: number;
  remaining_amount: number;
  stock?: number;
}

/**
 * Raw CarrierStats.SpaceUsage breakdown, every field optional because a
 * journal may report the capacity without the parts it is divided into.
 */
export interface CarrierSpaceUsage {
  total_capacity?: number | null;
  crew?: number | null;
  module_packs?: number | null;
  cargo?: number | null;
  cargo_space_reserved?: number | null;
  free_space?: number | null;
}

/**
 * The carrier's balances and the tax it charges for its services.
 *
 * Every field is optional: the journal has changed shape across game updates,
 * so a missing number means "not reported" and never zero.
 */
export interface CarrierFinance {
  carrier_balance?: number | null;
  reserve_balance?: number | null;
  available_balance?: number | null;
  reserve_percent?: number | null;
  tax_rate_rearm?: number | null;
  tax_rate_refuel?: number | null;
  tax_rate_repair?: number | null;
}

/**
 * One crew position aboard the carrier.
 *
 * A position exists whether or not it has been hired, which is what
 * `activated` says. `enabled` is the narrower question of whether a hired
 * service is currently switched on, and the journal reports it only for
 * activated roles.
 */
export interface CarrierCrewMember {
  role: string;
  activated: boolean;
  enabled?: boolean | null;
  name?: string | null;
}

/** How the carrier is running, as opposed to what it is carrying. */
export interface CarrierStatus {
  /** Tritium in the carrier's own tank, in tonnes. */
  fuel_level?: number | null;
  /** How far it can jump right now, in light years. */
  jump_range_current?: number | null;
  jump_range_max?: number | null;
  /** Scheduled to be scrapped, which ends with the carrier and its cargo gone. */
  pending_decommission: boolean;
  finance?: CarrierFinance | null;
  crew: CarrierCrewMember[];
}

export interface CarrierState {
  identity: CarrierIdentity;
  /**
   * Per-commodity carrier hold, largest tonnage first. Anchored on the
   * Market.json Stock column, which is the real hold rather than only what is
   * listed for sale, then carried forward by the commander's own market
   * transactions against the carrier.
   */
  cargo: CarrierCargoItem[];
  /**
   * When the Market.json export the hold is anchored on was written. The game
   * rewrites it on docking and opening the carrier's commodity market, so this
   * is how old the per-commodity view is. Null when no export was usable.
   */
  cargo_snapshot_time?: string | null;
  /**
   * total_cargo_tonnage minus the summed per-commodity hold. Zero means the
   * breakdown still agrees with the carrier's own total. Anything else is
   * tonnage moved by a route the journal does not record.
   */
  cargo_unaccounted_tonnage?: number | null;

  /**
   * Raw CarrierStats.SpaceUsage breakdown (when available).
   */
  space_usage?: CarrierSpaceUsage | null;
  /**
   * Total cargo tonnage in the carrier hold, taken from CarrierStats.SpaceUsage.Cargo
   * when available. This is the carrier's own total and is what the per-commodity
   * hold is checked against.
   */
  total_cargo_tonnage?: number | null;
  /**
   * Total carrier capacity in tonnes from CarrierStats.SpaceUsage.TotalCapacity when
   * available.
   */
  total_capacity_tonnage?: number | null;
  /**
   * Free cargo space in tonnes from CarrierStats.SpaceUsage.FreeSpace when available.
   * Together with total_cargo_tonnage this approximates the total cargo capacity
   * after accounting for installed services / loadouts.
   */
  free_space_tonnage?: number | null;
  buy_orders: CarrierOrder[];
  sell_orders: CarrierOrder[];
  /**
   * Indicates which journal window was used to derive buy/sell orders.
   * - since_docked: observed CarrierTradeOrder events after the latest Docked event
   * - recent_history: fallback window when no trade orders were observed since docking
   * - market_export: derived from Market.json snapshot (carrier market export)
   * - none: no trade order data available
   * - stale: trade order data exists but is older than the current docked context
   */
  trade_orders_scope?:
    | 'since_docked'
    | 'recent_history'
    | 'market_export'
    | 'stale'
    | 'none'
    | null;
  /**
   * Fuel, jump range, balances and crew, read from the same CarrierStats
   * event as the space usage. Null when no CarrierStats has been seen.
   */
  status?: CarrierStatus | null;
  snapshot_time: string;
}

export interface CurrentCarrierResponse {
  docked_at_carrier: boolean;
  carrier: CarrierIdentity | null;
}

export interface MyCarriersResponse {
  own_carriers: CarrierIdentity[];
  squadron_carriers: CarrierIdentity[];
}

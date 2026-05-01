/**
 * TypeScript types for Fleet carrier data.
 *
 * These mirror the backend models in backend/src/models/carriers.py and
 * backend/src/models/api_models.py so that the Fleet carriers UI can be
 * strongly typed.
 */

export type CarrierRole = 'own' | 'squadron' | 'other';

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

export interface CarrierState {
  identity: CarrierIdentity;
  cargo: CarrierCargoItem[];

  /**
   * Raw CarrierStats.SpaceUsage breakdown (when available).
   */
  space_usage?: {
    total_capacity?: number | null;
    crew?: number | null;
    module_packs?: number | null;
    cargo?: number | null;
    cargo_space_reserved?: number | null;
    free_space?: number | null;
  } | null;
  /**
   * Total cargo tonnage in the carrier hold, taken from CarrierStats.SpaceUsage.Cargo
   * when available. This may exceed the sum of per‑commodity market stock shown in
   * the cargo array, which only reflects commodities currently assigned to SELL orders.
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

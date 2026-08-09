/**
 * TypeScript types for colonisation data
 */

export enum CommodityStatus {
  COMPLETED = 'completed',
  IN_PROGRESS = 'in_progress',
  NOT_STARTED = 'not_started',
}

export interface Commodity {
  name: string;
  name_localised: string;
  required_amount: number;
  provided_amount: number;
  payment: number;
  remaining_amount: number;
  progress_percentage: number;
  status: CommodityStatus;
}

export interface ConstructionSite {
  market_id: number;
  station_name: string;
  station_type: string;
  system_name: string;
  system_address: number;
  construction_progress: number;
  construction_complete: boolean;
  construction_failed: boolean;
  commodities: Commodity[];
  last_updated: string;
  is_complete: boolean;
  total_commodities_needed: number;
  commodities_progress_percentage: number;
  last_source?: 'journal' | 'inara';
}

export interface SystemColonisationData {
  system_name: string;
  construction_sites: ConstructionSite[];
  total_sites: number;
  completed_sites: number;
  in_progress_sites: number;
  completion_percentage: number;
}

export interface CommodityAggregate {
  commodity_name: string;
  commodity_name_localised: string;
  total_required: number;
  total_provided: number;
  sites_requiring: string[];
  average_payment: number;
  total_remaining: number;
  progress_percentage: number;
}

export interface CurrentSystem {
  current_system: string | null;
  /**
   * Commander facts read on demand from the newest journal file: the name
   * (Commander event), the credit balance the session loaded with (LoadGame;
   * the journal records no running balance) and the docked context from the
   * newest of Docked/Undocked/FSDJump/Location. Each is null until a journal
   * carrying it is found.
   */
  commander_name?: string | null;
  credits_balance?: number | null;
  is_docked?: boolean | null;
  station_name?: string | null;
  station_type?: string | null;
}
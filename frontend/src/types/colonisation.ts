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
   * The commander's name, read from the latest journal file's Commander
   * event. Null until a journal with one is found.
   */
  commander_name?: string | null;
}
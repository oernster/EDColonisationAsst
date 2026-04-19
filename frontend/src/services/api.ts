import axios from 'axios';
import { SystemColonisationData, CurrentSystem } from '../types/colonisation';
import { AppSettings } from '../types/settings';
import {
  CarrierState,
  CurrentCarrierResponse,
  MyCarriersResponse,
} from '../types/fleetCarriers';
 
const API_BASE_URL = '/api';
 
export const api = {
  // Get all systems with construction
  async getSystems(): Promise<string[]> {
    const response = await axios.get<{ systems: string[] }>(`${API_BASE_URL}/systems`);
    return response.data.systems;
  },
 
  // Search systems by name
  async searchSystems(query: string): Promise<string[]> {
    const response = await axios.get<{ systems: string[] }>(`${API_BASE_URL}/systems/search`, {
      params: { q: query },
      paramsSerializer: params => {
        return Object.entries(params)
          .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
          .join('&');
      }
    });
    return response.data.systems;
  },
 
  // Get current player system
  async getCurrentSystem(): Promise<CurrentSystem> {
    const response = await axios.get<CurrentSystem>(`${API_BASE_URL}/journal/status`);
    return response.data;
  },
 
  // Get system colonisation data
  async getSystemData(systemName: string): Promise<SystemColonisationData> {
    const response = await axios.get<SystemColonisationData>(`${API_BASE_URL}/system`, {
      params: { name: systemName },
      paramsSerializer: params => {
        return Object.entries(params)
          .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
          .join('&');
      }
    });
    return response.data;
  },
 
  // Health check
  async healthCheck(): Promise<{ status: string; version: string; build_id: string; python_version: string }> {
    const response = await axios.get(`${API_BASE_URL}/health`);
    return response.data;
  },

  // Long-poll for backend change notifications (AJAX live updates)
  async longPollChanges(
    since: number,
    timeout_s: number = 25,
  ): Promise<{ seq: number; changed: boolean }> {
    const response = await axios.get<{ seq: number; changed: boolean }>(
      `${API_BASE_URL}/changes/longpoll`,
      {
        params: { since, timeout_s },
      },
    );
    return response.data;
  },
 
  // Get app settings
  async getAppSettings(): Promise<AppSettings> {
    const response = await axios.get<AppSettings>(`${API_BASE_URL}/settings`);
    return response.data;
  },
 
  // Update app settings
  async updateAppSettings(settings: AppSettings): Promise<AppSettings> {
    const response = await axios.post<AppSettings>(`${API_BASE_URL}/settings`, settings);
    return response.data;
  },

  // --- Fleet carriers ---

  // Are we currently docked at a carrier, and if so which one?
  async getCurrentCarrier(): Promise<CurrentCarrierResponse> {
    const response = await axios.get<CurrentCarrierResponse>(`${API_BASE_URL}/carriers/current`);
    return response.data;
  },

  // Full state (identity + cargo + orders) for the carrier we are docked at.
  async getCurrentCarrierState(): Promise<CarrierState | null> {
    const response = await axios.get<{ carrier: CarrierState | null }>(
      `${API_BASE_URL}/carriers/current/state`,
    );
    return response.data.carrier;
  },

  // List of own and squadron carriers inferred from recent journals.
  async getMyCarriers(): Promise<MyCarriersResponse> {
    const response = await axios.get<MyCarriersResponse>(`${API_BASE_URL}/carriers/mine`);
    return response.data;
  },
};

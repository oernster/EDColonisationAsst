import { create } from 'zustand';
import {
  CarrierState,
  CurrentCarrierResponse,
  MyCarriersResponse,
} from '../types/fleetCarriers';
import { api } from '../services/api';

interface CarrierStoreState {
  // Current docked carrier (real-time, based on latest journal events)
  currentCarrierInfo: CurrentCarrierResponse | null;
  currentCarrierState: CarrierState | null;

  // Last known carrier state, retained even after undocking so that recent
  // trade/cargo data remains visible in the UI.
  lastKnownCarrierState: CarrierState | null;

  currentCarrierLoading: boolean;
  currentCarrierError: string | null;

  // Own and squadron carriers
  myCarriers: MyCarriersResponse | null;
  myCarriersLoading: boolean;
  myCarriersError: string | null;

  // UI state: active Fleet Carrier detail tab
  carrierViewTab: 'cargo' | 'market';

  // Actions
  loadCurrentCarrier: () => Promise<void>;
  // Background refresh that does not toggle loading state or clear the UI.
  refreshCurrentCarrier: () => Promise<void>;
  // Refresh that *does* show loading state (manual user action).
  forceRefreshCurrentCarrier: () => Promise<void>;
  loadMyCarriers: () => Promise<void>;
  setCarrierViewTab: (tab: 'cargo' | 'market') => void;
  clearCarrierError: () => void;
}

export const useCarrierStore = create<CarrierStoreState>((set) => ({
  // Initial state
  currentCarrierInfo: null,
  currentCarrierState: null,
  lastKnownCarrierState: null,
  currentCarrierLoading: false,
  currentCarrierError: null,

  myCarriers: null,
  myCarriersLoading: false,
  myCarriersError: null,
  
  // UI state
  carrierViewTab: 'market',

  // Actions

  async loadCurrentCarrier() {
    try {
      set({
        currentCarrierLoading: true,
        currentCarrierError: null,
      });

      const info = await api.getCurrentCarrier();

      // If not docked at a carrier, clear the "current" state but retain the
      // last known carrier snapshot so that recent trading data remains
      // visible in the UI.
      if (!info.docked_at_carrier || !info.carrier) {
        set((prev) => ({
          currentCarrierInfo: info,
          currentCarrierState: null,
          // Preserve lastKnownCarrierState; we only update it when we have a
          // fresh non-null state from /carriers/current/state.
          lastKnownCarrierState: prev.lastKnownCarrierState,
          currentCarrierLoading: false,
        }));
        return;
      }

      const state = await api.getCurrentCarrierState();

      set((prev) => ({
        currentCarrierInfo: info,
        currentCarrierState: state,
        // Update the last-known snapshot whenever we have a real state.
        lastKnownCarrierState: state ?? prev.lastKnownCarrierState,
        currentCarrierLoading: false,
      }));
    } catch (error: any) {
      // 404 from /carriers/current/state just means "not docked at a carrier".
      const status = error?.response?.status;
      if (status === 404) {
        // "Not docked at a carrier" – keep any existing lastKnownCarrierState,
        // but clear the live currentCarrierState.
        set((prev) => ({
          currentCarrierState: null,
          lastKnownCarrierState: prev.lastKnownCarrierState,
          currentCarrierLoading: false,
          currentCarrierError: null,
        }));
        return;
      }

      set({
        currentCarrierLoading: false,
        currentCarrierError:
          error?.response?.data?.detail ||
          error?.message ||
          'Failed to load current carrier information',
      });
    }
  },

  async refreshCurrentCarrier() {
    try {
      const info = await api.getCurrentCarrier();

      // If not docked at a carrier, do not clear the current snapshot during
      // background refresh; just update the info.
      if (!info.docked_at_carrier || !info.carrier) {
        set((prev) => ({
          currentCarrierInfo: info,
          currentCarrierState: prev.currentCarrierState,
          lastKnownCarrierState: prev.lastKnownCarrierState,
        }));
        return;
      }

      const state = await api.getCurrentCarrierState();

      set((prev) => ({
        currentCarrierInfo: info,
        currentCarrierState: state,
        lastKnownCarrierState: state ?? prev.lastKnownCarrierState,
      }));
    } catch {
      // Background refresh errors are intentionally ignored; the last known
      // state remains visible and foreground loads surface errors instead.
    }
  },

  async forceRefreshCurrentCarrier() {
    // Reuse the foreground load path so the user can explicitly refresh and
    // see loading/error state if the backend is temporarily unavailable.
    await useCarrierStore.getState().loadCurrentCarrier();
  },

  async loadMyCarriers() {
    try {
      set({
        myCarriersLoading: true,
        myCarriersError: null,
      });

      const data = await api.getMyCarriers();

      set({
        myCarriers: data,
        myCarriersLoading: false,
      });
    } catch (error: any) {
      set({
        myCarriersLoading: false,
        myCarriersError:
          error?.response?.data?.detail ||
          error?.message ||
          'Failed to load carrier list',
      });
    }
  },

  setCarrierViewTab(tab) {
    set({ carrierViewTab: tab });
  },

  clearCarrierError() {
    set({
      currentCarrierError: null,
      myCarriersError: null,
    });
  },
}));

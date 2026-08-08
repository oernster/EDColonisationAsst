import { create } from 'zustand';
import {
  CarrierState,
  CurrentCarrierResponse,
  MyCarriersResponse,
} from '../types/fleetCarriers';
import { api } from '../services/api';
import {
  apiErrorDetail,
  apiErrorStatus,
  apiErrorText,
} from '../utils/apiError';

// Docking state is fetched optimistically: a 404 is the normal answer when
// the commander is not docked at a carrier, not a failure worth reporting.
const NOT_FOUND = 404;

/**
 * The detail views available for the carrier you are docked at.
 *
 * Named rather than indexed so that adding a view cannot silently renumber
 * the others.
 */
export type CarrierViewTab = 'market' | 'cargo' | 'status';

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
  carrierViewTab: CarrierViewTab;

  // Actions
  loadCurrentCarrier: () => Promise<void>;
  // Background refresh that does not toggle loading state or clear the UI.
  refreshCurrentCarrier: () => Promise<void>;
  // Refresh that *does* show loading state (manual user action).
  forceRefreshCurrentCarrier: () => Promise<void>;
  loadMyCarriers: () => Promise<void>;
  setCarrierViewTab: (tab: CarrierViewTab) => void;
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

      // Fetched whether or not the commander is aboard. Where the commander
      // stands does not change what their carrier is holding, and the state
      // says for itself whether they are on it.
      const state = await api.getCurrentCarrierState();

      set((prev) => ({
        currentCarrierInfo: info,
        currentCarrierState: state,
        // Update the last-known snapshot whenever we have a real state.
        lastKnownCarrierState: state ?? prev.lastKnownCarrierState,
        currentCarrierLoading: false,
      }));
    } catch (error: unknown) {
      // 404 from /carriers/current/state just means "not docked at a carrier".
      if (apiErrorStatus(error) === NOT_FOUND) {
        // "Not docked at a carrier": keep any existing lastKnownCarrierState
        // while clearing the live currentCarrierState.
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
          apiErrorDetail(error) ||
          apiErrorText(error) ||
          'Failed to load current carrier information',
      });
    }
  },

  async refreshCurrentCarrier() {
    try {
      const info = await api.getCurrentCarrier();

      // As above: the carrier's own state is worth refreshing wherever the
      // commander happens to be standing.
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
    } catch (error: unknown) {
      set({
        myCarriersLoading: false,
        myCarriersError:
          apiErrorDetail(error) ||
          apiErrorText(error) ||
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

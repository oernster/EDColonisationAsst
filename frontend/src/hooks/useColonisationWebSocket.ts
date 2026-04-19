import { useEffect, useRef } from 'react';
import type { SystemColonisationData } from '../types/colonisation';

/**
 * Lightweight WebSocket client for live colonisation updates.
 *
 * It connects to `/ws/colonisation`, subscribes to the currently selected
 * system, and updates the colonisation store whenever UPDATE messages arrive.
 *
 * The hook is intentionally conservative: it keeps the REST-driven initial
 * snapshot (via /api/system) and only applies incremental updates on top.
 */
export function useColonisationWebSocket(
  currentSystem: string | null,
  setSystemData: (data: SystemColonisationData | null) => void,
  setError: (message: string | null) => void,
  onRefresh?: () => void,
): void {
  const wsRef = useRef<WebSocket | null>(null);
  const subscribedSystemRef = useRef<string | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const onRefreshRef = useRef<(() => void) | undefined>(onRefresh);

  // Keep the latest callback without forcing WebSocket reconnection.
  useEffect(() => {
    onRefreshRef.current = onRefresh;
  }, [onRefresh]);

  // Establish and manage the WebSocket connection tied to the app lifecycle.
  useEffect(() => {
    let cancelled = false;
    let reconnectDelayMs = 1000;

    const connect = () => {
      if (cancelled || wsRef.current) {
        return;
      }

      try {
        const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const url = `${wsScheme}://${window.location.host}/ws/colonisation`;

        const socket = new WebSocket(url);
        wsRef.current = socket;

        socket.onopen = () => {
          reconnectDelayMs = 1000; // reset backoff on successful connection
          // Subscribe to the current system if one is selected.
          if (currentSystem) {
            const message = JSON.stringify({
              type: 'subscribe',
              system_name: currentSystem,
            });
            socket.send(message);
            subscribedSystemRef.current = currentSystem;
          }
        };

        socket.onmessage = (event: MessageEvent) => {
          try {
            const payload = JSON.parse(event.data);

            const msgType = String(payload.type || '').toLowerCase();

            if (msgType === 'update') {
              const systemName: string | undefined = payload.system_name;
              const data = payload.data;

              if (!systemName || !data) {
                return;
              }

              // Only apply updates for the system that is currently selected.
              if (systemName !== currentSystem) {
                return;
              }

              // The backend sends a payload that is structurally compatible with
              // SystemColonisationData minus system_name. We rehydrate it here.
              const updated: SystemColonisationData = {
                system_name: systemName,
                construction_sites: data.construction_sites ?? [],
                total_sites: data.total_sites ?? 0,
                completed_sites: data.completed_sites ?? 0,
                in_progress_sites: data.in_progress_sites ?? 0,
                completion_percentage: data.completion_percentage ?? 0,
              };

              setSystemData(updated);
            } else if (msgType === 'refresh') {
              // Global refresh hint from the backend (e.g. after bulk journal reload).
              // The caller decides what to refetch.
              try {
                onRefreshRef.current?.();
              } catch {
                // Ignore callback errors.
              }
            } else if (msgType === 'error') {
              // Surface WebSocket-level errors as a non-fatal message in the UI.
              const message: string =
                payload.error || 'WebSocket error receiving colonisation updates';
              setError(message);
            } else if (msgType === 'pong') {
              // No-op; reserved for future heartbeat handling.
            }
          } catch {
            // Ignore malformed messages; they should not break the UI.
          }
        };

        socket.onerror = () => {
          // Let onclose handle reconnection logic; avoid spamming UI errors.
        };

        socket.onclose = () => {
          wsRef.current = null;
          subscribedSystemRef.current = null;

          if (cancelled) {
            return;
          }

          // Basic bounded exponential backoff for reconnect.
          const delay = reconnectDelayMs;
          reconnectDelayMs = Math.min(reconnectDelayMs * 2, 30000);

          if (typeof window !== 'undefined') {
            reconnectTimeoutRef.current = window.setTimeout(connect, delay);
          }
        };
      } catch {
        // If constructing WebSocket fails (very old browser or unusual env),
        // do not throw; simply leave live updates disabled.
      }
    };

    connect();

    return () => {
      cancelled = true;

      if (reconnectTimeoutRef.current !== null && typeof window !== 'undefined') {
        window.clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }

      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch {
          // Ignore close errors
        }
        wsRef.current = null;
      }

      subscribedSystemRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Connection lifetime is tied to the App/root, not to currentSystem changes.

  // Keep the server-side subscription in sync with the currently selected system.
  useEffect(() => {
    const socket = wsRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    const previous = subscribedSystemRef.current;

    if (previous && previous !== currentSystem) {
      const unsubscribeMessage = JSON.stringify({
        type: 'unsubscribe',
        system_name: previous,
      });
      try {
        socket.send(unsubscribeMessage);
      } catch {
        // Ignore send failures; connection will either be closed or retried by the other effect.
      }
      subscribedSystemRef.current = null;
    }

    if (currentSystem && currentSystem !== subscribedSystemRef.current) {
      const subscribeMessage = JSON.stringify({
        type: 'subscribe',
        system_name: currentSystem,
      });
      try {
        socket.send(subscribeMessage);
        subscribedSystemRef.current = currentSystem;
      } catch {
        // Ignore send failures; reconnection logic will attempt again after backoff.
      }
    }
  }, [currentSystem, setSystemData, setError]);
}

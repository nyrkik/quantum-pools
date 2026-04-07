"use client";

import React, { createContext, useContext, useEffect, useRef, useCallback, useState } from "react";
import { getBackendOrigin } from "./api";

// ── Event Types ─────────────────────────────────────────────────────

export type WSEventType =
  | "thread.new"
  | "thread.updated"
  | "thread.read"
  | "thread.message.new"
  | "message.new"
  | "message.read"
  | "notification.new"
  | "visit.started"
  | "visit.completed"
  | "case.updated"
  | "data.changed"
  | "ping"
  | "connected"
  | "replay";

export interface WSEvent {
  id?: string;
  type: WSEventType;
  org_id?: string;
  user_id?: string;
  data?: Record<string, unknown>;
  timestamp?: number;
  stream_id?: string;
  events?: WSEvent[]; // for replay type
}

type WSEventHandler = (event: WSEvent) => void;

// ── WebSocket Manager ───────────────────────────────────────────────

class WebSocketManager {
  private ws: WebSocket | null = null;
  private listeners = new Map<string, Set<WSEventHandler>>();
  private wildcardListeners = new Set<WSEventHandler>();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 20;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private lastStreamId: string | null = null;
  private _isConnected = false;
  private pingTimer: ReturnType<typeof setInterval> | null = null;

  get isConnected() {
    return this._isConnected;
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    const origin = getBackendOrigin();
    const wsProtocol = origin.startsWith("https") ? "wss" : "ws";
    const host = origin.replace(/^https?:\/\//, "");
    let url = `${wsProtocol}://${host}/api/v1/ws`;

    if (this.lastStreamId) {
      url += `?last_stream_id=${encodeURIComponent(this.lastStreamId)}`;
    }

    try {
      this.ws = new WebSocket(url);
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this._isConnected = true;
      this.reconnectAttempts = 0;
      this.emit("connected", { type: "connected" } as WSEvent);

      // Respond to server pings
      this.pingTimer = setInterval(() => {
        if (this.ws?.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify({ type: "pong" }));
        }
      }, 25000);
    };

    this.ws.onmessage = (event) => {
      try {
        const data: WSEvent = JSON.parse(event.data);

        // Track stream ID for replay on reconnect
        if (data.stream_id) {
          this.lastStreamId = data.stream_id;
        }

        // Handle replay: emit each event individually
        if (data.type === "replay" && data.events) {
          for (const evt of data.events) {
            if (evt.stream_id) this.lastStreamId = evt.stream_id;
            this.emit(evt.type, evt);
          }
          return;
        }

        // Server ping — just track, don't emit to listeners
        if (data.type === "ping") {
          return;
        }

        this.emit(data.type, data);
      } catch {
        // Ignore malformed messages
      }
    };

    this.ws.onclose = (event) => {
      this._isConnected = false;
      this.cleanupPing();
      // Don't reconnect on intentional close (4001 = auth failed)
      if (event.code !== 4001) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      // onclose will fire after onerror
    };
  }

  disconnect() {
    this.cleanupPing();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close(1000, "Client disconnect");
      this.ws = null;
    }
    this._isConnected = false;
    this.reconnectAttempts = 0;
  }

  private cleanupPing() {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;

    // Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    this.reconnectAttempts++;

    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  on(eventType: string, handler: WSEventHandler): () => void {
    if (eventType === "*") {
      this.wildcardListeners.add(handler);
      return () => this.wildcardListeners.delete(handler);
    }

    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    this.listeners.get(eventType)!.add(handler);
    return () => this.listeners.get(eventType)?.delete(handler);
  }

  off(eventType: string, handler: WSEventHandler) {
    if (eventType === "*") {
      this.wildcardListeners.delete(handler);
    } else {
      this.listeners.get(eventType)?.delete(handler);
    }
  }

  private emit(eventType: string, event: WSEvent) {
    // Typed listeners
    const handlers = this.listeners.get(eventType);
    if (handlers) {
      for (const handler of handlers) {
        try {
          handler(event);
        } catch {
          // Don't let one bad handler break others
        }
      }
    }
    // Wildcard listeners
    for (const handler of this.wildcardListeners) {
      try {
        handler(event);
      } catch {
        // Don't let one bad handler break others
      }
    }
  }
}

// Singleton instance
const wsManager = new WebSocketManager();

// ── React Context ───────────────────────────────────────────────────

interface WSContextValue {
  isConnected: boolean;
  subscribe: (eventType: WSEventType | "*", handler: WSEventHandler) => () => void;
}

const WSContext = createContext<WSContextValue>({
  isConnected: false,
  subscribe: () => () => {},
});

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    wsManager.connect();

    const unsub = wsManager.on("connected", () => {
      setIsConnected(true);
    });

    // Track disconnects
    const checkInterval = setInterval(() => {
      setIsConnected(wsManager.isConnected);
    }, 5000);

    return () => {
      unsub();
      clearInterval(checkInterval);
      wsManager.disconnect();
    };
  }, []);

  const subscribe = useCallback((eventType: WSEventType | "*", handler: WSEventHandler) => {
    return wsManager.on(eventType, handler);
  }, []);

  return (
    <WSContext.Provider value={{ isConnected, subscribe }}>
      {children}
    </WSContext.Provider>
  );
}

// ── Hooks ───────────────────────────────────────────────────────────

/** Subscribe to one or more WebSocket event types. */
export function useWSEvent(
  eventTypes: WSEventType | WSEventType[],
  handler: WSEventHandler,
  deps: React.DependencyList = [],
) {
  const { subscribe } = useContext(WSContext);
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    const types = Array.isArray(eventTypes) ? eventTypes : [eventTypes];
    const unsubs = types.map((type) =>
      subscribe(type, (event) => handlerRef.current(event)),
    );
    return () => unsubs.forEach((unsub) => unsub());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subscribe, ...deps]);
}

/** Get WebSocket connection status. */
export function useWSStatus() {
  const { isConnected } = useContext(WSContext);
  return { isConnected };
}

/**
 * Subscribe to events and trigger a refetch callback.
 * Debounces rapid-fire events (e.g. multiple thread updates in quick succession).
 */
export function useWSRefetch(
  eventTypes: WSEventType | WSEventType[],
  refetch: () => void,
  debounceMs = 500,
) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refetchRef = useRef(refetch);
  refetchRef.current = refetch;

  useWSEvent(
    eventTypes,
    () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => refetchRef.current(), debounceMs);
    },
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);
}

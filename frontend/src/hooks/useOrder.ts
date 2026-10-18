"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getApiErrorMessage } from "@/lib/errors";
import * as ordersApi from "@/services/orders";
import type { Order } from "@/types/order";

export interface UseOrder {
  /** null until loaded (or if it could not be loaded). */
  order: Order | null;
  isLoading: boolean;
  /** Message from the last failed load (for example "Order was not found."), else null. */
  error: string | null;
  reload: () => Promise<void>;
  /** Cancels the order and stores the cancelled order the server returns.
   * REJECTS on failure (message also in `cancelError`). A second call while
   * one is in flight returns the same promise. */
  cancel: () => Promise<Order>;
  isCancelling: boolean;
  cancelError: string | null;
}

/**
 * Loads one of the user's orders. The server only ever answers for the
 * logged-in user's own orders, so another customer's id comes back as an
 * error, never as data. A response for a previous id is ignored if the id
 * has changed since.
 */
export function useOrder(orderId: string): UseOrder {
  const [order, setOrder] = useState<Order | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  const idRef = useRef(orderId);
  const requestRef = useRef(0);
  const cancelling = useRef<Promise<Order> | null>(null);

  const load = useCallback(async () => {
    const request = ++requestRef.current;
    const id = idRef.current;
    setIsLoading(true);
    setError(null);
    try {
      const loaded = await ordersApi.getOrder(id);
      if (requestRef.current === request && idRef.current === id) setOrder(loaded);
    } catch (err) {
      if (requestRef.current === request && idRef.current === id) {
        setOrder(null);
        setError(getApiErrorMessage(err, "We couldn't load this order. Please try again."));
      }
    } finally {
      if (requestRef.current === request) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    idRef.current = orderId;
    requestRef.current += 1;
    cancelling.current = null;
    setOrder(null);
    setError(null);
    setCancelError(null);
    setIsCancelling(false);
    void load();
  }, [orderId, load]);

  const cancel = useCallback((): Promise<Order> => {
    if (cancelling.current !== null) return cancelling.current;
    const id = idRef.current;
    setCancelError(null);
    setIsCancelling(true);

    const attempt = (async (): Promise<Order> => {
      try {
        const cancelled = await ordersApi.cancelOrder(id);
        if (idRef.current === id) setOrder(cancelled);
        return cancelled;
      } catch (err) {
        if (idRef.current === id) {
          setCancelError(getApiErrorMessage(err, "We couldn't cancel this order. Please try again."));
          // The order may have changed under us (e.g. a payment landed): show the truth.
          void load();
        }
        throw err;
      } finally {
        cancelling.current = null;
        setIsCancelling(false);
      }
    })();

    cancelling.current = attempt;
    return attempt;
  }, [load]);

  return { order, isLoading, error, reload: load, cancel, isCancelling, cancelError };
}

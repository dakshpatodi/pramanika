"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/context/AuthContext";
import { getApiErrorMessage } from "@/lib/errors";
import { listAddresses } from "@/services/addresses";
import { listInvoices } from "@/services/invoices";
import { listOrders } from "@/services/orders";
import { listWishlist } from "@/services/wishlist";
import type { OrderList } from "@/types/order";

/** One block of the overview. Each loads, fails and retries on its own, so one
 * slow or broken endpoint never blanks the rest of the page. */
export type Section<T> = { status: "loading" } | { status: "ready"; data: T } | { status: "error"; message: string };

export type SectionKey = "orders" | "wishlist" | "addresses" | "invoices";

export interface DashboardOverview {
  /** The three most recent orders, plus the total number of orders. */
  orders: Section<OrderList>;
  wishlist: Section<number>;
  addresses: Section<number>;
  invoices: Section<number>;
  /** Reload one section (its own Retry button). */
  retry: (key: SectionKey) => void;
}

export const RECENT_ORDERS = 3;

const LOADERS = {
  orders: () => listOrders(1, RECENT_ORDERS),
  // Page size 1: only `pagination.total` is wanted, not the items.
  wishlist: async () => (await listWishlist(1, 1)).pagination.total,
  addresses: async () => (await listAddresses()).length,
  invoices: async () => (await listInvoices(1, 1)).pagination.total,
} as const;

const FAILURE: Record<SectionKey, string> = {
  orders: "We couldn't load your orders.",
  wishlist: "We couldn't load your wishlist.",
  addresses: "We couldn't load your addresses.",
  invoices: "We couldn't load your invoices.",
};

const KEYS: SectionKey[] = ["orders", "wishlist", "addresses", "invoices"];

const LOADING: Section<never> = { status: "loading" };

/**
 * Real numbers for the account overview, all from the existing APIs. Forgets
 * everything when the signed-in user changes, and ignores any response that
 * arrives after the user changed or after a newer request for the same block.
 */
export function useDashboardOverview(): DashboardOverview {
  const { user, isLoading: isAuthLoading } = useAuth();
  const userId = user?.id ?? null;

  const [state, setState] = useState<{
    orders: Section<OrderList>;
    wishlist: Section<number>;
    addresses: Section<number>;
    invoices: Section<number>;
  }>({ orders: LOADING, wishlist: LOADING, addresses: LOADING, invoices: LOADING });

  const ownerRef = useRef<string | null>(null);
  const requestRef = useRef<Record<SectionKey, number>>({ orders: 0, wishlist: 0, addresses: 0, invoices: 0 });

  const load = useCallback(async (key: SectionKey) => {
    const request = ++requestRef.current[key];
    const owner = ownerRef.current;
    setState((current) => ({ ...current, [key]: LOADING }));
    const isCurrent = () => requestRef.current[key] === request && ownerRef.current === owner;
    try {
      const data = await LOADERS[key]();
      if (isCurrent()) setState((current) => ({ ...current, [key]: { status: "ready", data } }));
    } catch (error) {
      if (isCurrent()) {
        setState((current) => ({ ...current, [key]: { status: "error", message: getApiErrorMessage(error, FAILURE[key]) } }));
      }
    }
  }, []);

  useEffect(() => {
    ownerRef.current = userId;
    for (const key of KEYS) requestRef.current[key] += 1; // invalidates anything still in flight
    setState({ orders: LOADING, wishlist: LOADING, addresses: LOADING, invoices: LOADING });
    if (isAuthLoading || userId === null) return;
    for (const key of KEYS) void load(key);
  }, [userId, isAuthLoading, load]);

  const retry = useCallback((key: SectionKey) => void load(key), [load]);

  return { ...state, retry };
}

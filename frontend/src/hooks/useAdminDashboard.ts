"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/context/AuthContext";
import { getApiErrorMessage } from "@/lib/errors";
import { getAdminDashboard } from "@/services/admin";
import type { AdminDashboard } from "@/types/admin";

export interface AdminDashboardState {
  data: AdminDashboard | null;
  /** True while a request is in flight (first load or a refresh). */
  loading: boolean;
  /** The last request's failure. `data` may still hold the previous numbers. */
  error: string | null;
  reload: () => void;
}

/**
 * The admin overview numbers. A refresh keeps showing the previous numbers until
 * the new ones arrive (or fail), and a response that arrives after the user
 * changed, or after a newer request, is ignored.
 */
export function useAdminDashboard(): AdminDashboardState {
  const { user, isLoading: isAuthLoading } = useAuth();
  const userId = user?.id ?? null;

  const [data, setData] = useState<AdminDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const ownerRef = useRef<string | null>(null);
  const requestRef = useRef(0);

  const load = useCallback(async () => {
    const request = ++requestRef.current;
    const owner = ownerRef.current;
    setLoading(true);
    setError(null);
    const isCurrent = () => requestRef.current === request && ownerRef.current === owner;
    try {
      const next = await getAdminDashboard();
      if (isCurrent()) {
        setData(next);
        setLoading(false);
      }
    } catch (failure) {
      if (isCurrent()) {
        setError(getApiErrorMessage(failure, "We couldn't load the dashboard."));
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    ownerRef.current = userId;
    requestRef.current += 1; // invalidates anything still in flight
    setData(null);
    setError(null);
    setLoading(true);
    if (isAuthLoading || userId === null) return;
    void load();
  }, [userId, isAuthLoading, load]);

  const reload = useCallback(() => void load(), [load]);

  return { data, loading, error, reload };
}

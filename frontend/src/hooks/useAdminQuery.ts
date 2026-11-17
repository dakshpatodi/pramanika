"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/context/AuthContext";
import { getApiErrorMessage } from "@/lib/errors";

export interface AdminQuery<T> {
  data: T | null;
  /** True while a request is in flight (first load, a new page/filter, or a reload). */
  loading: boolean;
  /** The last request's failure; `data` may still hold the previous result. */
  error: string | null;
  reload: () => void;
  /** Replace the data (e.g. with the server's copy after a save) without a request. */
  setData: (next: T) => void;
}

interface Options {
  /** Message when the failure carries none of its own. */
  failure: string;
  /** Keep showing the previous result while a different key loads (lists: yes; one item: no). */
  keepPrevious?: boolean;
}

/**
 * One admin read. Re-fetches when `key` changes (pass null to not fetch), ignores a response that
 * arrives after a newer request or after the signed-in user changed, and forgets everything when
 * the user changes. `fetcher` may be a new function every render; the latest one is used.
 */
export function useAdminQuery<T>(key: string | null, fetcher: () => Promise<T>, options: Options): AdminQuery<T> {
  const { user, isLoading: isAuthLoading } = useAuth();
  const userId = user?.id ?? null;
  const keepPrevious = options.keepPrevious ?? false;
  const failure = options.failure;

  const [data, setDataState] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const ownerRef = useRef<string | null>(null);
  const requestRef = useRef(0);

  const load = useCallback(async () => {
    const request = ++requestRef.current;
    const owner = ownerRef.current;
    setLoading(true);
    setError(null);
    const isCurrent = () => requestRef.current === request && ownerRef.current === owner;
    try {
      const next = await fetcherRef.current();
      if (isCurrent()) {
        setDataState(next);
        setLoading(false);
      }
    } catch (caught) {
      if (isCurrent()) {
        setError(getApiErrorMessage(caught, failure));
        setLoading(false);
      }
    }
  }, [failure]);

  const lastOwner = useRef<string | null>(null);
  useEffect(() => {
    ownerRef.current = userId;
    requestRef.current += 1; // invalidates anything still in flight
    const sameOwner = lastOwner.current === userId;
    lastOwner.current = userId;
    if (!(keepPrevious && sameOwner)) setDataState(null);
    setError(null);
    setLoading(true);
    if (isAuthLoading || userId === null || key === null) return;
    void load();
  }, [key, userId, isAuthLoading, keepPrevious, load]);

  const reload = useCallback(() => void load(), [load]);
  const setData = useCallback((next: T) => setDataState(next), []);

  return { data, loading, error, reload, setData };
}

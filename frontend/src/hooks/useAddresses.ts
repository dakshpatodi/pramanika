"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/context/AuthContext";
import { getApiErrorMessage } from "@/lib/errors";
import * as addressApi from "@/services/addresses";
import type { Address, AddressInput } from "@/types/address";

export interface UseAddresses {
  /** The user's addresses, default first; null until the first load finishes. */
  addresses: Address[] | null;
  isLoading: boolean;
  /** Message from the last failed load, else null. */
  loadError: string | null;
  reload: () => Promise<void>;
  /** Saves a new address and resolves with it; REJECTS on failure (the
   * server's validation message is in the error). The list is reloaded so
   * the default flag stays right when the new address became the default. */
  addAddress: (input: AddressInput) => Promise<Address>;
}

/**
 * Loads the logged-in user's addresses and adds new ones. Forgets
 * everything when the user changes, and ignores a response that arrives
 * after a newer request (or after logout).
 */
export function useAddresses(): UseAddresses {
  const { user, isLoading: isAuthLoading } = useAuth();
  const userId = user?.id ?? null;

  const [addresses, setAddresses] = useState<Address[] | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const ownerRef = useRef<string | null>(null);
  const requestRef = useRef(0);

  const reload = useCallback(async () => {
    const request = ++requestRef.current;
    const owner = ownerRef.current;
    setIsLoading(true);
    setLoadError(null);
    try {
      const list = await addressApi.listAddresses();
      if (requestRef.current === request && ownerRef.current === owner) setAddresses(list);
    } catch (error) {
      if (requestRef.current === request && ownerRef.current === owner) {
        setLoadError(getApiErrorMessage(error, "We couldn't load your addresses. Please try again."));
      }
    } finally {
      if (requestRef.current === request) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    ownerRef.current = userId;
    requestRef.current += 1;
    setAddresses(null);
    setLoadError(null);
    setIsLoading(false);
    if (isAuthLoading || userId === null) return;
    void reload();
  }, [userId, isAuthLoading, reload]);

  const addAddress = useCallback(
    async (input: AddressInput): Promise<Address> => {
      const created = await addressApi.createAddress(input);
      await reload();
      return created;
    },
    [reload]
  );

  return { addresses, isLoading, loadError, reload, addAddress };
}
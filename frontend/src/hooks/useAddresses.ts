"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/context/AuthContext";
import { getApiErrorMessage } from "@/lib/errors";
import * as addressApi from "@/services/addresses";
import type { Address, AddressInput, AddressUpdateInput } from "@/types/address";

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
  /** Saves the changed fields of one address and resolves with it; REJECTS on failure. */
  updateAddress: (id: string, input: AddressUpdateInput) => Promise<Address>;
  /** Makes one address the default; REJECTS on failure. */
  makeDefault: (id: string) => Promise<void>;
  /** Deletes one address (the server promotes another default if needed); REJECTS on failure. */
  removeAddress: (id: string) => Promise<void>;
}

/**
 * Loads the logged-in user's addresses and changes them. Forgets
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

  /** Show what the server just answered, unless the user changed meanwhile. Also
   * cancels any older list request still in flight so it cannot overwrite this. */
  const apply = useCallback((owner: string | null, update: (current: Address[] | null) => Address[] | null) => {
    if (ownerRef.current !== owner) return;
    requestRef.current += 1;
    setIsLoading(false);
    setLoadError(null);
    setAddresses(update);
  }, []);

  const addAddress = useCallback(
    async (input: AddressInput): Promise<Address> => {
      const created = await addressApi.createAddress(input);
      await reload();
      return created;
    },
    [reload]
  );

  const updateAddress = useCallback(
    async (id: string, input: AddressUpdateInput): Promise<Address> => {
      const owner = ownerRef.current;
      const updated = await addressApi.updateAddress(id, input);
      apply(owner, (current) => (current ? current.map((a) => (a.id === updated.id ? updated : a)) : current));
      return updated;
    },
    [apply]
  );

  const makeDefault = useCallback(
    async (id: string): Promise<void> => {
      const owner = ownerRef.current;
      const list = await addressApi.setDefaultAddress(id);
      apply(owner, () => list);
    },
    [apply]
  );

  const removeAddress = useCallback(
    async (id: string): Promise<void> => {
      const owner = ownerRef.current;
      const list = await addressApi.deleteAddress(id);
      apply(owner, () => list);
    },
    [apply]
  );

  return { addresses, isLoading, loadError, reload, addAddress, updateAddress, makeDefault, removeAddress };
}

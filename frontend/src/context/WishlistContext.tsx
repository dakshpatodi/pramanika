"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "@/context/AuthContext";
import { getApiErrorMessage } from "@/lib/errors";
import * as wishlistApi from "@/services/wishlist";

export interface WishlistContextValue {
  /** False outside a WishlistProvider. Heart buttons render nothing then, so a
   * screen that shows product cards never needs the provider just to mount. */
  isAvailable: boolean;
  /** True once a user is logged in. Guests are sent to log in instead. */
  isAuthenticated: boolean;
  /** True while the session or the saved-product ids are still loading. */
  isLoading: boolean;
  /** Message from the last failed load of the saved-product ids, else null. */
  loadError: string | null;
  /** How many products are saved (the server allows at most 100). */
  count: number;
  isSaved: (productId: string) => boolean;
  /** True while a save/remove for this product is in flight. */
  isPending: (productId: string) => boolean;
  /** Save / remove / flip. They update the heart at once and, if the server
   * refuses (wishlist full, product withdrawn, offline...), put it back and
   * REJECT - callers show `getApiErrorMessage(err)`. `toggle` resolves to the
   * new saved state. A call for a product already in flight does nothing. */
  add: (productId: string) => Promise<void>;
  remove: (productId: string) => Promise<void>;
  toggle: (productId: string) => Promise<boolean>;
  /** Records a change made elsewhere (no request is sent). */
  setSaved: (productId: string, saved: boolean) => void;
  refresh: () => Promise<void>;
}

const unavailable = async (): Promise<never> => {
  throw new Error("The wishlist is not available here.");
};

const UNAVAILABLE: WishlistContextValue = {
  isAvailable: false,
  isAuthenticated: false,
  isLoading: false,
  loadError: null,
  count: 0,
  isSaved: () => false,
  isPending: () => false,
  add: unavailable,
  remove: unavailable,
  toggle: unavailable,
  setSaved: () => {},
  refresh: async () => {},
};

const WishlistContext = createContext<WishlistContextValue>(UNAVAILABLE);

function withMember(set: ReadonlySet<string>, id: string, present: boolean): ReadonlySet<string> {
  if (set.has(id) === present) return set;
  const next = new Set(set);
  if (present) next.add(id);
  else next.delete(id);
  return next;
}

/**
 * Owns the one copy of "which products has this user saved" so every heart on
 * the page agrees. Only ids live here; the full wishlist page loads its own
 * pages of details.
 *
 * Must sit INSIDE AuthProvider: ids are loaded when a user is logged in and
 * thrown away the moment they log out or a different user logs in, so one
 * person's hearts can never show up for another. A response for a previous
 * user is discarded.
 */
export function WishlistProvider({ children }: { children: React.ReactNode }) {
  const { user, isLoading: isAuthLoading } = useAuth();
  const userId = user?.id ?? null;

  const [ids, setIds] = useState<ReadonlySet<string>>(() => new Set());
  const [pending, setPending] = useState<ReadonlySet<string>>(() => new Set());
  const [isLoadingIds, setIsLoadingIds] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const ownerRef = useRef<string | null>(null); // whose wishlist the in-flight requests are for
  const loadRef = useRef(0); // latest id fetch, so only it clears the loading flag
  const idsRef = useRef<ReadonlySet<string>>(ids);
  const pendingRef = useRef<ReadonlySet<string>>(pending);

  const commitIds = useCallback((next: ReadonlySet<string>) => {
    idsRef.current = next;
    setIds(next);
  }, []);
  const commitPending = useCallback((next: ReadonlySet<string>) => {
    pendingRef.current = next;
    setPending(next);
  }, []);

  const fetchIds = useCallback(async () => {
    const owner = ownerRef.current;
    if (owner === null) return;
    const load = ++loadRef.current;
    setIsLoadingIds(true);
    setLoadError(null);
    try {
      const productIds = await wishlistApi.getWishlistProductIds();
      if (ownerRef.current === owner && loadRef.current === load) {
        // A heart tapped while this was loading keeps the value the user chose.
        let next: ReadonlySet<string> = new Set(productIds);
        for (const id of pendingRef.current) next = withMember(next, id, idsRef.current.has(id));
        commitIds(next);
      }
    } catch (error) {
      if (ownerRef.current === owner && loadRef.current === load) {
        setLoadError(getApiErrorMessage(error, "We couldn't load your wishlist. Please try again."));
      }
    } finally {
      if (loadRef.current === load) setIsLoadingIds(false);
    }
  }, [commitIds]);

  // Whenever the logged-in user changes (login, logout, switch): forget the
  // previous user's wishlist and, if someone is logged in, load theirs.
  useEffect(() => {
    ownerRef.current = userId;
    loadRef.current += 1;
    commitIds(new Set());
    commitPending(new Set());
    setLoadError(null);
    setIsLoadingIds(false);

    if (isAuthLoading || userId === null) return;
    void fetchIds();
  }, [userId, isAuthLoading, fetchIds, commitIds, commitPending]);

  const mutate = useCallback(
    async (productId: string, wantSaved: boolean): Promise<void> => {
      const owner = ownerRef.current;
      if (owner === null) throw new Error("Please log in to use your wishlist.");
      if (pendingRef.current.has(productId)) return;

      const wasSaved = idsRef.current.has(productId);
      commitPending(withMember(pendingRef.current, productId, true));
      commitIds(withMember(idsRef.current, productId, wantSaved));
      try {
        if (wantSaved) await wishlistApi.addToWishlist(productId);
        else await wishlistApi.removeFromWishlist(productId);
      } catch (error) {
        if (ownerRef.current === owner) commitIds(withMember(idsRef.current, productId, wasSaved));
        throw error;
      } finally {
        if (ownerRef.current === owner) commitPending(withMember(pendingRef.current, productId, false));
      }
    },
    [commitIds, commitPending]
  );

  const value = useMemo<WishlistContextValue>(
    () => ({
      isAvailable: true,
      isAuthenticated: userId !== null,
      isLoading: isAuthLoading || isLoadingIds,
      loadError,
      count: ids.size,
      isSaved: (productId) => ids.has(productId),
      isPending: (productId) => pending.has(productId),
      add: (productId) => mutate(productId, true),
      remove: (productId) => mutate(productId, false),
      toggle: async (productId) => {
        if (pendingRef.current.has(productId)) return idsRef.current.has(productId);
        const next = !idsRef.current.has(productId);
        await mutate(productId, next);
        return next;
      },
      setSaved: (productId, saved) => commitIds(withMember(idsRef.current, productId, saved)),
      refresh: fetchIds,
    }),
    [userId, isAuthLoading, isLoadingIds, loadError, ids, pending, mutate, commitIds, fetchIds]
  );

  return <WishlistContext.Provider value={value}>{children}</WishlistContext.Provider>;
}

/** Never throws: outside a provider it returns an inert value (`isAvailable: false`). */
export function useWishlist(): WishlistContextValue {
  return useContext(WishlistContext);
}

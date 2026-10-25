"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Heart } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useWishlist } from "@/context/WishlistContext";
import { getApiErrorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";

interface WishlistButtonProps {
  productId: string;
  productName: string;
  /** "icon": a heart over a product card. "text": a labelled button for the product page. */
  variant?: "icon" | "text";
  /** Where a guest returns to after logging in (a path on this site). */
  redirectTo: string;
  className?: string;
}

/** How long a failure message stays up before it clears itself. */
const ERROR_MS = 5000;

const ICON_BUTTON =
  "flex h-9 w-9 items-center justify-center rounded-full border border-border bg-card/95 text-foreground shadow-card transition-colors hover:text-accent-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary aria-disabled:cursor-wait aria-disabled:opacity-60";

/**
 * Save / un-save one product.
 *
 * - Renders nothing outside a WishlistProvider.
 * - Guests get a link to log in (and come back); nothing is sent for them.
 *   While the session is still loading a disabled button stands in, so a
 *   logged-in user never sees a login link flash up.
 * - Logged in: the heart flips at once and is put back, with the server's
 *   message, if the request fails. While it is in flight (or the saved ids are
 *   still loading) it ignores clicks; it uses aria-disabled rather than
 *   `disabled` so keyboard focus is not lost mid-click.
 * - The button's name says what a click will do ("Save ... / Remove ..."), and
 *   a visually hidden status line announces the result.
 */
export function WishlistButton({ productId, productName, variant = "icon", redirectTo, className }: WishlistButtonProps) {
  const wishlist = useWishlist();
  const [error, setError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    if (error === null) return;
    const timer = setTimeout(() => setError(null), ERROR_MS);
    return () => clearTimeout(timer);
  }, [error]);

  if (!wishlist.isAvailable) return null;

  const loginHref = `/login?redirect=${encodeURIComponent(redirectTo)}`;
  const saved = wishlist.isSaved(productId);
  const busy = wishlist.isLoading || wishlist.isPending(productId);
  // While the session is still loading nobody is known to be a guest, so no login link yet.
  const showLogin = !wishlist.isAuthenticated && !wishlist.isLoading;
  const label = saved ? "Remove from wishlist" : "Save to wishlist";

  async function handleClick() {
    if (busy) return;
    setError(null);
    setAnnouncement("");
    try {
      const nowSaved = await wishlist.toggle(productId);
      setAnnouncement(nowSaved ? `${productName} saved to your wishlist.` : `${productName} removed from your wishlist.`);
    } catch (err) {
      setError(getApiErrorMessage(err, "We couldn't update your wishlist. Please try again."));
    }
  }

  const status = (
    <span role="status" className="sr-only">
      {announcement}
    </span>
  );
  const alert =
    error === null ? null : variant === "icon" ? (
      <p
        role="alert"
        className="absolute bottom-full right-0 z-20 mb-2 w-max max-w-[9rem] rounded-xl border border-border bg-card px-3 py-2 text-xs text-foreground shadow-lift"
      >
        {error}
      </p>
    ) : (
      <p role="alert" className="text-sm text-foreground">
        {error}
      </p>
    );

  if (variant === "icon") {
    return (
      <div className={cn("relative", className)}>
        {!showLogin ? (
          <button
            type="button"
            onClick={() => void handleClick()}
            aria-label={`${label}: ${productName}`}
            aria-disabled={busy || undefined}
            className={ICON_BUTTON}
          >
            <Heart className={cn("h-4 w-4", saved && "fill-current text-accent-dark")} aria-hidden="true" />
          </button>
        ) : (
          <Link
            href={loginHref}
            aria-label={`Log in to save to wishlist: ${productName}`}
            className={ICON_BUTTON}
          >
            <Heart className="h-4 w-4" aria-hidden="true" />
          </Link>
        )}
        {status}
        {alert}
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col items-start gap-2", className)}>
      {!showLogin ? (
        <Button type="button" variant="outline" onClick={() => void handleClick()} aria-disabled={busy || undefined} className="aria-disabled:cursor-wait aria-disabled:opacity-60">
          <Heart className={cn(saved && "fill-current text-accent-dark")} aria-hidden="true" /> {label}
        </Button>
      ) : (
        <Button variant="outline" asChild>
          <Link href={loginHref}>
            <Heart aria-hidden="true" /> Save to wishlist
          </Link>
        </Button>
      )}
      {status}
      {alert}
    </div>
  );
}

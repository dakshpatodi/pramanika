"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, Check, Heart, ShoppingCart, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useCart } from "@/context/CartContext";
import { useWishlist } from "@/context/WishlistContext";
import { getApiErrorMessage } from "@/lib/errors";
import { formatPrice } from "@/lib/utils";
import type { WishlistItem } from "@/types/wishlist";

interface WishlistItemCardProps {
  item: WishlistItem;
  /** Called after the server has removed the product, so the page can reload its list. */
  onRemoved: () => void;
}

type Feedback = { type: "success" | "error"; message: string } | null;

/**
 * One saved product: its current name, price and availability (from the
 * server, never from a stored copy), with Add to cart and Remove.
 *
 * A product that has been withdrawn from sale stays listed so it can be
 * removed, but it is not linked and cannot be added to the cart.
 */
export function WishlistItemCard({ item, onRemoved }: WishlistItemCardProps) {
  const { addItem } = useCart();
  const wishlist = useWishlist();
  const [busy, setBusy] = useState<"cart" | "remove" | null>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);

  const canBuy = item.is_available && item.in_stock;

  async function handleAddToCart() {
    if (busy) return;
    setFeedback(null);
    setBusy("cart");
    try {
      await addItem(item.product_id, 1);
      setFeedback({ type: "success", message: `Added ${item.name} to your cart.` });
    } catch (error) {
      // e.g. "Only 5 units are available in stock." - the server decides.
      setFeedback({ type: "error", message: getApiErrorMessage(error, "We couldn't add this to your cart. Please try again.") });
    } finally {
      setBusy(null);
    }
  }

  async function handleRemove() {
    if (busy) return;
    setFeedback(null);
    setBusy("remove");
    try {
      await wishlist.remove(item.product_id);
      onRemoved();
    } catch (error) {
      setFeedback({ type: "error", message: getApiErrorMessage(error, "We couldn't remove this from your wishlist. Please try again.") });
    } finally {
      setBusy(null);
    }
  }

  const title = item.is_available ? (
    <Link href={`/shop/${item.slug}`} className="font-display text-base font-semibold text-foreground hover:text-primary">
      {item.name}
    </Link>
  ) : (
    <span className="font-display text-base font-semibold text-foreground">{item.name}</span>
  );

  return (
    <Card className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start">
      <span aria-hidden="true" className="flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl bg-primary-light text-primary">
        <Heart className="h-8 w-8" strokeWidth={1.5} />
      </span>

      <div className="flex min-w-0 flex-1 flex-col gap-2">
        {title}
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-display text-lg font-semibold text-foreground">{formatPrice(item.price)}</span>
          {item.compare_at_price ? (
            <span className="text-sm text-muted-foreground line-through">{formatPrice(item.compare_at_price)}</span>
          ) : null}
        </div>

        <div>
          {!item.is_available ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-foreground/80 px-3 py-1 text-xs font-semibold text-background">
              <XCircle className="h-3.5 w-3.5" aria-hidden="true" /> No longer available
            </span>
          ) : !item.in_stock ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-foreground/80 px-3 py-1 text-xs font-semibold text-background">
              <XCircle className="h-3.5 w-3.5" aria-hidden="true" /> Out of stock
            </span>
          ) : item.low_stock ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-3 py-1 text-xs font-semibold text-secondary-foreground">
              <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> Only a few left
            </span>
          ) : null}
        </div>

        {feedback ? (
          feedback.type === "success" ? (
            <p role="status" className="flex flex-wrap items-center gap-x-2 text-sm font-medium text-primary">
              <Check className="h-4 w-4" aria-hidden="true" /> {feedback.message}
              <Link href="/cart" className="font-semibold underline underline-offset-4 hover:text-primary-dark">
                View cart
              </Link>
            </p>
          ) : (
            <p role="alert" className="flex items-start gap-2 text-sm text-foreground">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-accent-dark" aria-hidden="true" /> {feedback.message}
            </p>
          )
        ) : null}
      </div>

      <div className="flex flex-wrap gap-2 sm:flex-col sm:items-stretch">
        {canBuy ? (
          <Button type="button" variant="primary" size="sm" onClick={() => void handleAddToCart()} disabled={busy !== null} aria-label={`Add ${item.name} to cart`}>
            <ShoppingCart aria-hidden="true" /> {busy === "cart" ? "Adding..." : "Add to cart"}
          </Button>
        ) : null}
        <Button type="button" variant="outline" size="sm" onClick={() => void handleRemove()} disabled={busy !== null} aria-label={`Remove ${item.name} from wishlist`}>
          {busy === "remove" ? "Removing..." : "Remove"}
        </Button>
      </div>
    </Card>
  );
}

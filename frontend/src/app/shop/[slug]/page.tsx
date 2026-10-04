"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, Check, Minus, Plus, ShoppingCart, XCircle } from "lucide-react";

import { ProductCard } from "@/components/products/ProductCard";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { useCart } from "@/context/CartContext";
import { getCategoryIcon } from "@/lib/category-icons";
import { getApiErrorMessage } from "@/lib/errors";
import { formatPrice } from "@/lib/utils";
import { getProduct } from "@/services/products";
import type { ProductDetail } from "@/types/product";

/** The cart API rejects a single request for more than this many units. */
const MAX_QUANTITY = 1000;

export default function ProductDetailPage() {
  const params = useParams<{ slug: string }>();

  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [quantity, setQuantity] = useState(1);
  const [isAdding, setIsAdding] = useState(false);
  const [feedback, setFeedback] = useState<{ productId: string; type: "success" | "error"; message: string } | null>(
    null
  );

  const router = useRouter();
  const pathname = usePathname();
  const { isAuthenticated, isLoading: isAuthLoading } = useAuth();
  const { addItem } = useCart();

  async function handleAddToCart() {
    if (!product) return;

    // Carts belong to accounts. Send guests to log in and bring them
    // straight back to this product afterwards.
    if (!isAuthenticated) {
      router.push(`/login?redirect=${encodeURIComponent(pathname)}`);
      return;
    }

    const productId = product.id;
    const added = quantity;
    setFeedback(null);
    setIsAdding(true);
    try {
      await addItem(productId, added);
      setQuantity(1);
      setFeedback({
        productId,
        type: "success",
        message: `Added ${added} \u00d7 ${product.name} to your cart.`,
      });
    } catch (error) {
      // e.g. "Only 5 units are available in stock." - the server decides.
      setFeedback({
        productId,
        type: "error",
        message: getApiErrorMessage(error, "We couldn't add this to your cart. Please try again."),
      });
    } finally {
      setIsAdding(false);
    }
  }

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);
    setNotFound(false);
    setFeedback(null);
    setQuantity(1);

    getProduct(params.slug)
      .then((data) => {
        if (isMounted) setProduct(data);
      })
      .catch(() => {
        if (isMounted) setNotFound(true);
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [params.slug]);

  if (isLoading) {
    return (
      <div className="container py-16">
        <div className="grid grid-cols-1 gap-10 md:grid-cols-2">
          <div className="aspect-square animate-pulse rounded-2xl bg-muted" />
          <div className="flex flex-col gap-4">
            <div className="h-6 w-1/3 animate-pulse rounded bg-muted" />
            <div className="h-9 w-2/3 animate-pulse rounded bg-muted" />
            <div className="h-24 animate-pulse rounded bg-muted" />
          </div>
        </div>
      </div>
    );
  }

  if (notFound || !product) {
    return (
      <div className="container flex flex-col items-center gap-4 py-24 text-center">
        <span className="flex h-16 w-16 items-center justify-center rounded-blob bg-muted text-muted-foreground">
          <XCircle className="h-8 w-8" />
        </span>
        <h1 className="font-display text-2xl font-semibold text-foreground">Product not found</h1>
        <p className="max-w-sm text-muted-foreground">This product may have been removed, or the link is incorrect.</p>
        <Button variant="primary" asChild>
          <Link href="/shop">Back to Shop</Link>
        </Button>
      </div>
    );
  }

  const Icon = getCategoryIcon(product.category.slug);

  return (
    <div className="container flex flex-col gap-16 py-12">
      <div>
        <Link
          href="/shop"
          className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-primary"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Shop
        </Link>

        <div className="grid grid-cols-1 gap-10 md:grid-cols-2">
          {/* Image placeholder - no real product photography yet, same
              situation Phase 1's homepage was in. */}
          <div className="relative flex aspect-square items-center justify-center rounded-2xl bg-primary-light">
            {product.compare_at_price ? (
              <span className="absolute left-4 top-4 rounded-full bg-accent px-3 py-1 text-xs font-semibold text-accent-foreground">
                Sale
              </span>
            ) : null}
            <Icon className="h-32 w-32 text-primary" strokeWidth={1.25} />
          </div>

          {/* Info */}
          <div className="flex flex-col gap-5">
            <div className="flex flex-col gap-2">
              <Link
                href={`/shop?category=${product.category.slug}`}
                className="text-xs font-semibold uppercase tracking-wide text-primary hover:underline"
              >
                {product.category.name}
              </Link>
              <h1 className="font-display text-3xl font-semibold text-foreground">{product.name}</h1>
              {product.short_description ? <p className="text-muted-foreground">{product.short_description}</p> : null}
            </div>

            <div className="flex items-baseline gap-3">
              <span className="font-display text-3xl font-semibold text-foreground">{formatPrice(product.price)}</span>
              {product.compare_at_price ? (
                <span className="text-lg text-muted-foreground line-through">
                  {formatPrice(product.compare_at_price)}
                </span>
              ) : null}
            </div>

            <div>
              {!product.in_stock ? (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-foreground/80 px-3 py-1.5 text-xs font-semibold text-background">
                  <XCircle className="h-3.5 w-3.5" /> Out of stock
                </span>
              ) : product.low_stock ? (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-3 py-1.5 text-xs font-semibold text-secondary-foreground">
                  <AlertTriangle className="h-3.5 w-3.5" /> Only a few left
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-primary-light px-3 py-1.5 text-xs font-semibold text-primary">
                  <Check className="h-3.5 w-3.5" /> In stock
                </span>
              )}
            </div>

                {/* Quantity selector + Add to Cart. The server checks stock and
                decides how many can be added; its message is shown below. */}
            {product.in_stock ? (
              <div className="flex items-center gap-4">
                <div className="flex items-center rounded-full border border-border">
                  <button
                    type="button"
                    onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                    className="flex h-11 w-11 items-center justify-center text-foreground hover:text-primary"
                    aria-label="Decrease quantity"
                  >
                    <Minus className="h-4 w-4" />
                  </button>
                  <span className="w-8 text-center text-sm font-semibold">{quantity}</span>
                  <button
                    type="button"
                    onClick={() => setQuantity((q) => Math.min(MAX_QUANTITY, q + 1))}
                    className="flex h-11 w-11 items-center justify-center text-foreground hover:text-primary"
                    aria-label="Increase quantity"
                  >
                    <Plus className="h-4 w-4" />
                  </button>
                </div>

                <Button
                  variant="primary"
                  size="lg"
                  className="flex-1"
                  onClick={handleAddToCart}
                  disabled={isAdding || isAuthLoading}
                >
                  <ShoppingCart className="h-4 w-4" /> {isAdding ? "Adding..." : "Add to Cart"}
                </Button>
              </div>
            ) : null}

            {product.in_stock && !isAuthenticated && !isAuthLoading ? (
              <p className="text-sm text-muted-foreground">Log in to add items to your cart.</p>
            ) : null}

            {feedback && feedback.productId === product.id ? (
              feedback.type === "success" ? (
                <p role="status" className="flex flex-wrap items-center gap-x-2 text-sm font-medium text-primary">
                  <Check className="h-4 w-4" /> {feedback.message}
                  <Link href="/cart" className="font-semibold underline underline-offset-4 hover:text-primary-dark">
                    View cart
                  </Link>
                </p>
              ) : (
                <p role="alert" className="flex items-start gap-2 text-sm text-foreground">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-accent-dark" /> {feedback.message}
                </p>
              )
            ) : null}

            <dl className="grid grid-cols-2 gap-4 border-t border-border pt-5 text-sm">
              <div>
                <dt className="text-muted-foreground">SKU</dt>
                <dd className="font-medium text-foreground">{product.sku}</dd>
              </div>
              {product.weight ? (
                <div>
                  <dt className="text-muted-foreground">Weight</dt>
                  <dd className="font-medium text-foreground">
                    {product.weight}
                    {product.weight_unit}
                  </dd>
                </div>
              ) : null}
            </dl>

            {product.description ? (
              <div className="flex flex-col gap-1.5 border-t border-border pt-5">
                <h2 className="font-display text-base font-semibold text-foreground">Description</h2>
                <p className="text-sm text-muted-foreground">{product.description}</p>
              </div>
            ) : null}

            {product.ingredients ? (
              <div className="flex flex-col gap-1.5 border-t border-border pt-5">
                <h2 className="font-display text-base font-semibold text-foreground">Ingredients</h2>
                <p className="text-sm text-muted-foreground">{product.ingredients}</p>
              </div>
            ) : null}

            {product.nutritional_information ? (
              <div className="flex flex-col gap-1.5 border-t border-border pt-5">
                <h2 className="font-display text-base font-semibold text-foreground">Nutritional Information</h2>
                <p className="text-sm text-muted-foreground">{product.nutritional_information}</p>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {product.related_products.length > 0 ? (
        <div className="flex flex-col gap-6">
          <h2 className="font-display text-2xl font-semibold text-foreground">You might also like</h2>
          <div className="grid grid-cols-2 gap-4 sm:gap-6 lg:grid-cols-4">
            {product.related_products.map((related) => (
              <ProductCard key={related.id} product={related} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
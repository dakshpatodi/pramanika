"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Heart } from "lucide-react";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { WishlistItemCard } from "@/components/dashboard/WishlistItemCard";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useWishlistItems } from "@/hooks/useWishlistItems";

const PAGE_SIZE = 12;

function WishlistContent() {
  const [page, setPage] = useState(1);
  const { data, isLoading, error, reload } = useWishlistItems(page, PAGE_SIZE);

  // Removing the last item of a later page leaves that page empty: step back.
  const totalPages = data?.pagination.total_pages ?? 0;
  useEffect(() => {
    if (totalPages >= 1 && page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  let body: React.ReactNode;
  if (!data && error) {
    body = (
      <Card className="flex flex-col items-center gap-4 px-6 py-14 text-center">
        <p role="alert" className="max-w-sm text-foreground">
          {error}
        </p>
        <Button variant="primary" onClick={() => void reload()} disabled={isLoading}>
          {isLoading ? "Retrying..." : "Try again"}
        </Button>
      </Card>
    );
  } else if (!data) {
    body = (
      <div role="status" aria-label="Loading your wishlist" className="flex flex-col gap-4">
        {[0, 1, 2].map((n) => (
          <div key={n} className="h-32 animate-pulse rounded-2xl bg-muted" />
        ))}
      </div>
    );
  } else if (data.pagination.total === 0) {
    body = (
      <Card className="flex flex-col items-center gap-3 px-6 py-16 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-blob bg-primary-light text-primary">
          <Heart className="h-7 w-7" aria-hidden="true" />
        </span>
        <h2 className="font-display text-xl font-semibold text-foreground">Your wishlist is empty</h2>
        <p className="max-w-sm text-sm text-muted-foreground">Tap the heart on a product to save it here for later.</p>
        <Button variant="primary" asChild>
          <Link href="/shop">Browse the shop</Link>
        </Button>
      </Card>
    );
  } else {
    const { items, pagination } = data;
    body = (
      <div className="flex flex-col gap-4">
        {error ? (
          <p role="alert" className="text-sm text-accent-dark">
            {error}
          </p>
        ) : null}
        <ul aria-busy={isLoading} className="flex flex-col gap-4">
          {items.map((item) => (
            <li key={item.product_id}>
              <WishlistItemCard item={item} onRemoved={() => void reload()} />
            </li>
          ))}
        </ul>

        {pagination.total_pages > 1 ? (
          <nav aria-label="Wishlist pages" className="flex items-center justify-between gap-3">
            <Button variant="outline" size="sm" disabled={!pagination.has_previous || isLoading} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {pagination.page} of {pagination.total_pages}
            </span>
            <Button variant="outline" size="sm" disabled={!pagination.has_next || isLoading} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </nav>
        ) : null}
      </div>
    );
  }

  return (
    <DashboardShell title="Wishlist" description="Products you have saved for later.">
      {body}
    </DashboardShell>
  );
}

export default function WishlistPage() {
  return (
    <ProtectedRoute>
      <WishlistContent />
    </ProtectedRoute>
  );
}

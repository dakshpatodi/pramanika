/** Placeholder shown while the first cart fetch is in flight. */
export function CartSkeleton() {
  return (
    <div
      className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]"
      role="status"
      aria-label="Loading your cart"
    >
      <div className="flex flex-col gap-5 rounded-2xl border border-border bg-card p-6 shadow-card">
        {[0, 1].map((n) => (
          <div key={n} className="flex gap-4">
            <div className="h-20 w-20 animate-pulse rounded-xl bg-muted" />
            <div className="flex flex-1 flex-col gap-2">
              <div className="h-5 w-1/2 animate-pulse rounded bg-muted" />
              <div className="h-4 w-1/4 animate-pulse rounded bg-muted" />
              <div className="mt-2 h-9 w-28 animate-pulse rounded-full bg-muted" />
            </div>
          </div>
        ))}
      </div>
      <div className="h-72 animate-pulse rounded-2xl bg-muted" />
    </div>
  );
}
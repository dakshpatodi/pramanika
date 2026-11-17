import { PackageOpen } from "lucide-react";

import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";

/** Placeholder rows while a list loads for the first time. */
export function ListSkeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-3">
      {[0, 1, 2, 3].map((n) => (
        <div key={n} className="h-14 animate-pulse rounded-xl bg-muted" />
      ))}
    </div>
  );
}

/** A failed load, with the reason and a way to try again. */
export function ListError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-start gap-3">
      <Banner>{message}</Banner>
      <Button type="button" variant="outline" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}

/** Nothing to show: either nothing exists yet, or the filters match nothing. */
export function ListEmpty({ title, hint, action }: { title: string; hint?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 py-10 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-blob bg-primary-light text-primary">
        <PackageOpen className="h-6 w-6" aria-hidden="true" />
      </span>
      <p className="font-medium text-foreground">{title}</p>
      {hint ? <p className="text-sm text-muted-foreground">{hint}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

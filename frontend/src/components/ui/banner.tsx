import { AlertTriangle } from "lucide-react";

/** A highlighted notice (errors, warnings). Announced to screen readers. */
export function Banner({ children }: { children: React.ReactNode }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl bg-accent-light px-4 py-3 text-sm text-foreground">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-accent-dark" aria-hidden="true" />
      <div className="flex-1">{children}</div>
    </div>
  );
}

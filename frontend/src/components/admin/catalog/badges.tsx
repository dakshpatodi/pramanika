import type { StockStatus } from "@/types/admin-catalog";

const PILL = "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium";

/** Active / Inactive as words (never colour alone). */
export function ActiveBadge({ active }: { active: boolean }) {
  return (
    <span className={`${PILL} ${active ? "bg-primary-light text-primary-dark" : "bg-muted text-muted-foreground"}`}>
      {active ? "Active" : "Inactive"}
    </span>
  );
}

const STOCK: Record<StockStatus, { label: string; style: string }> = {
  ok: { label: "In stock", style: "bg-primary-light text-primary-dark" },
  low: { label: "Low stock", style: "bg-secondary-light text-foreground" },
  out: { label: "Out of stock", style: "bg-accent-light text-accent-dark" },
};

export function StockBadge({ status }: { status: StockStatus }) {
  const { label, style } = STOCK[status];
  return <span className={`${PILL} ${style}`}>{label}</span>;
}

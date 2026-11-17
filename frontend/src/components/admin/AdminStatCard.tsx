import Link from "next/link";

import { Card } from "@/components/ui/card";

interface AdminStatCardProps {
  label: string;
  value: React.ReactNode;
  /** A short line under the number ("12 paid orders"). */
  hint?: React.ReactNode;
  /** Draws the number in the warning colour (e.g. out of stock > 0). */
  tone?: "default" | "warning";
  /** Short links under the number to the page that explains it ("View orders"). */
  links?: Array<{ href: string; label: string }>;
}

/** One headline number. `role="group"` + label so a screen reader reads "Orders, 42". */
export function AdminStatCard({ label, value, hint, tone = "default", links }: AdminStatCardProps) {
  return (
    <Card role="group" aria-label={label} className="p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p
        className={`mt-2 font-display text-3xl font-semibold ${tone === "warning" ? "text-accent-dark" : "text-foreground"}`}
      >
        {value}
      </p>
      {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
      {links && links.length > 0 ? (
        <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs font-medium">
          {links.map((link) => (
            <Link key={link.href} href={link.href} className="text-primary hover:underline">
              {link.label}
            </Link>
          ))}
        </p>
      ) : null}
    </Card>
  );
}

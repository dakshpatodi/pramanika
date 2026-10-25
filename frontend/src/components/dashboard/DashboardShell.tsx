"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { DASHBOARD_NAV, isActiveNavItem } from "@/components/dashboard/dashboard-nav";
import { cn } from "@/lib/utils";

interface DashboardShellProps {
  /** The page's one visible heading. Leave it out when the page draws its own `<h1>`
   * (the order detail page does), so there is never more than one. */
  title?: string;
  description?: string;
  children: React.ReactNode;
}

/**
 * The frame around every account page: a heading (unless the page has its own) and the account menu (a
 * sidebar on wide screens, a scrollable row on narrow ones).
 *
 * It does not check the session. Each page wraps itself in ProtectedRoute,
 * as before, so protected content is never rendered for a visitor.
 */
export function DashboardShell({ title, description, children }: DashboardShellProps) {
  const pathname = usePathname();

  return (
    <div className="container py-10">
      {title ? (
        <div className="mb-8">
          <h1 className="font-display text-3xl font-semibold text-foreground">{title}</h1>
          {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
        </div>
      ) : null}

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:gap-10">
        <nav aria-label="Account" className="lg:w-56 lg:shrink-0">
          <ul className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1 lg:mx-0 lg:flex-col lg:overflow-visible lg:px-0 lg:pb-0">
            {DASHBOARD_NAV.map((item) => {
              const active = isActiveNavItem(item, pathname);
              const Icon = item.icon;
              return (
                <li key={item.href} className="shrink-0">
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-3 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                      active ? "bg-primary-light text-primary" : "text-foreground/80 hover:bg-muted hover:text-primary"
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}

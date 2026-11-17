"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { ADMIN_NAV, isActiveAdminItem, type AdminNavItem } from "@/components/admin/admin-nav";
import { cn } from "@/lib/utils";

interface AdminShellProps {
  children: React.ReactNode;
  /** Defaults to the real menu; tests pass their own. */
  items?: AdminNavItem[];
}

/**
 * The frame around every admin page: an "Admin" menu (a sidebar on wide screens,
 * a scrollable row on narrow ones) and the page. Pages draw their own `<h1>`
 * with AdminPageHeader. It does not check access - AdminRoute does that.
 */
export function AdminShell({ children, items = ADMIN_NAV }: AdminShellProps) {
  const pathname = usePathname();

  return (
    <div className="container py-8">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:gap-10">
        <nav aria-label="Admin" className="lg:w-56 lg:shrink-0">
          <p className="mb-2 hidden px-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground lg:block">
            Administration
          </p>
          <ul className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1 lg:mx-0 lg:flex-col lg:overflow-visible lg:px-0 lg:pb-0">
            {items.map((item) => {
              const active = isActiveAdminItem(item, pathname);
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

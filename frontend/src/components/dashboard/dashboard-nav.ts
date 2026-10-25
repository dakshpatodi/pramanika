import { FileText, Heart, LayoutDashboard, MapPin, Package, User, type LucideIcon } from "lucide-react";

export interface DashboardNavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  /** Pages that count as "inside" this item (e.g. /orders/123 highlights Orders). */
  matchPrefix: boolean;
}

/**
 * The account pages, in the order they appear in the menu. Only pages that
 * exist are listed.
 */
export const DASHBOARD_NAV: DashboardNavItem[] = [
  { label: "Overview", href: "/dashboard", icon: LayoutDashboard, matchPrefix: false },
  { label: "Profile", href: "/profile", icon: User, matchPrefix: true },
  { label: "Orders", href: "/orders", icon: Package, matchPrefix: true },
  { label: "Wishlist", href: "/dashboard/wishlist", icon: Heart, matchPrefix: true },
  { label: "Saved addresses", href: "/dashboard/addresses", icon: MapPin, matchPrefix: true },
  { label: "Invoices", href: "/dashboard/invoices", icon: FileText, matchPrefix: true },
];

export function isActiveNavItem(item: Pick<DashboardNavItem, "href" | "matchPrefix">, pathname: string | null): boolean {
  if (!pathname) return false;
  if (pathname === item.href) return true;
  return item.matchPrefix && pathname.startsWith(`${item.href}/`);
}

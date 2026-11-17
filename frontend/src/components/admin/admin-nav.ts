import { Boxes, ClipboardList, LayoutDashboard, Tags, Warehouse, type LucideIcon } from "lucide-react";

export interface AdminNavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  /** Pages that count as "inside" this item (e.g. /admin/orders/123 highlights Orders). */
  matchPrefix: boolean;
}

/**
 * The admin pages, in menu order. Only pages that exist are listed.
 */
export const ADMIN_NAV: AdminNavItem[] = [
  { label: "Overview", href: "/admin", icon: LayoutDashboard, matchPrefix: false },
  { label: "Orders", href: "/admin/orders", icon: ClipboardList, matchPrefix: true },
  { label: "Products", href: "/admin/products", icon: Boxes, matchPrefix: true },
  { label: "Categories", href: "/admin/categories", icon: Tags, matchPrefix: true },
  { label: "Inventory", href: "/admin/inventory", icon: Warehouse, matchPrefix: true },
];

export function isActiveAdminItem(item: Pick<AdminNavItem, "href" | "matchPrefix">, pathname: string | null): boolean {
  if (!pathname) return false;
  if (pathname === item.href) return true;
  return item.matchPrefix && pathname.startsWith(`${item.href}/`);
}

"use client";

import { AdminRoute } from "@/components/admin/AdminRoute";
import { AdminShell } from "@/components/admin/AdminShell";

/**
 * Every page under /admin sits inside this layout, so the access check and the
 * admin menu apply to all of them - a new admin page cannot forget the guard.
 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminRoute>
      <AdminShell>{children}</AdminShell>
    </AdminRoute>
  );
}

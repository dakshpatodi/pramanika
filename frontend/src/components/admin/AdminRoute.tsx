"use client";

import Link from "next/link";
import { ShieldAlert } from "lucide-react";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { useAdminAccess } from "@/hooks/useAdminAccess";

function Checking() {
  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center">
      <div
        role="status"
        aria-label="Checking your access"
        className="h-10 w-10 animate-spin rounded-full border-4 border-border border-t-primary"
      />
    </div>
  );
}

function AccessDenied() {
  return (
    <div className="container flex min-h-[calc(100vh-4rem)] items-center justify-center py-10">
      <div className="flex max-w-md flex-col items-center gap-4 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-blob bg-accent-light text-accent-dark">
          <ShieldAlert className="h-7 w-7" aria-hidden="true" />
        </span>
        <h1 className="font-display text-2xl font-semibold text-foreground">You don&apos;t have access to this page</h1>
        <p className="text-sm text-muted-foreground">
          The admin area is only for store administrators. If you think you should have access, ask an existing
          administrator.
        </p>
        <Button variant="primary" asChild>
          <Link href="/">Back to the shop</Link>
        </Button>
      </div>
    </div>
  );
}

function AdminGate({ children }: { children: React.ReactNode }) {
  const { access, retry } = useAdminAccess();

  if (access.status === "checking") return <Checking />;
  if (access.status === "forbidden") return <AccessDenied />;
  if (access.status === "error") {
    return (
      <div className="container py-10">
        <div className="mx-auto flex max-w-md flex-col items-start gap-4">
          <Banner>{access.message}</Banner>
          <Button type="button" variant="outline" onClick={retry}>
            Try again
          </Button>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}

/**
 * Wrap admin pages in this (the /admin layout does, so every page under it is
 * covered without remembering). Signed out -> /login (and back here afterwards);
 * signed in but not an admin -> a plain "no access" page; admin -> the content.
 *
 * `children` are never rendered until the server has confirmed the role, so
 * admin screens (and their API calls) never start for anyone else. The server
 * enforces the same rule on every /api/admin request regardless of this.
 */
export function AdminRoute({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedRoute>
      <AdminGate>{children}</AdminGate>
    </ProtectedRoute>
  );
}

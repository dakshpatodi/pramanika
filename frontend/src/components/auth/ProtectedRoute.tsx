"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/context/AuthContext";

interface ProtectedRouteProps {
  children: React.ReactNode;
}

/**
 * Wrap any page's content in this to require authentication.
 *
 * Redirects to /login (preserving the original destination via a
 * `redirect` query param, so login can send the user back where they
 * were headed) once the session-restore check finishes and no user is
 * logged in.
 *
 * Deliberately does NOT render `children` at all while loading or
 * unauthenticated - not even hidden via CSS - so protected content is
 * never briefly present in the DOM for an unauthenticated visitor to
 * inspect (e.g. via dev tools) before the redirect actually fires.
 */
export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push(`/login?redirect=${encodeURIComponent(pathname)}`);
    }
  }, [isLoading, isAuthenticated, pathname, router]);

  if (isLoading) {
    return (
      <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-border border-t-primary" />
      </div>
    );
  }

  if (!isAuthenticated) {
    // Redirect above is already in flight (useEffect) - render nothing
    // in the meantime rather than a flash of protected content.
    return null;
  }

  return <>{children}</>;
}
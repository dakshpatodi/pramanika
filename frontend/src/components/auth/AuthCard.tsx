import Link from "next/link";
import { Leaf } from "lucide-react";

interface AuthCardProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

/**
 * Shared visual shell for /login and /register: logo mark, heading, a
 * card containing the form, and an optional footer line (the
 * "don't have an account? / already have one?" cross-link). Keeps each
 * page's own file focused entirely on its form logic.
 */
export function AuthCard({ title, subtitle, children, footer }: AuthCardProps) {
  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <Link
            href="/"
            className="flex h-12 w-12 items-center justify-center rounded-blob bg-primary text-primary-foreground"
          >
            <Leaf className="h-6 w-6" strokeWidth={2} />
          </Link>
          <h1 className="font-display text-2xl font-semibold text-foreground">{title}</h1>
          {subtitle ? <p className="max-w-sm text-sm text-muted-foreground">{subtitle}</p> : null}
        </div>

        <div className="rounded-2xl border border-border bg-card p-6 shadow-card sm:p-8">{children}</div>

        {footer ? <div className="mt-6 text-center text-sm text-muted-foreground">{footer}</div> : null}
      </div>
    </div>
  );
}
"use client";

import { CalendarDays, Clock, LogOut, Mail, Phone, ShieldCheck } from "lucide-react";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";

function formatDate(value: string | null): string {
  if (!value) return "Never";
  return new Date(value).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function ProfileContent() {
  const { user, logout } = useAuth();

  // ProtectedRoute guarantees `user` is populated by the time this ever
  // renders (isAuthenticated is derived from `user !== null` - see
  // AuthContext) - this guard is purely for TypeScript's benefit, since
  // it can't see that external invariant from inside this component.
  if (!user) return null;

  const fullName = `${user.first_name} ${user.last_name}`;
  const initials = `${user.first_name[0] ?? ""}${user.last_name[0] ?? ""}`.toUpperCase();

  const details = [
    { icon: Mail, label: "Email", value: user.email },
    { icon: Phone, label: "Phone", value: user.phone_number },
    { icon: CalendarDays, label: "Member since", value: formatDate(user.created_at) },
    { icon: Clock, label: "Last login", value: formatDate(user.last_login) },
  ];

  return (
    <div className="container flex justify-center py-16">
      <div className="w-full max-w-2xl">
        <div className="rounded-2xl border border-border bg-card p-8 shadow-card">
          <div className="flex flex-col items-center gap-4 border-b border-border pb-8 text-center sm:flex-row sm:text-left">
            <span className="flex h-20 w-20 shrink-0 items-center justify-center rounded-blob bg-primary text-2xl font-semibold text-primary-foreground">
              {initials}
            </span>
            <div className="flex flex-col gap-2">
              <h1 className="font-display text-2xl font-semibold text-foreground">{fullName}</h1>
              <div className="flex flex-wrap items-center justify-center gap-2 sm:justify-start">
                <span className="rounded-full bg-primary-light px-3 py-1 text-xs font-semibold capitalize text-primary">
                  {user.role}
                </span>
                <span
                  className={
                    user.is_active
                      ? "rounded-full bg-primary-light px-3 py-1 text-xs font-semibold text-primary"
                      : "rounded-full bg-accent/10 px-3 py-1 text-xs font-semibold text-accent-dark"
                  }
                >
                  {user.is_active ? "Active" : "Deactivated"}
                </span>
                {user.is_verified ? (
                  <span className="flex items-center gap-1 rounded-full bg-secondary/20 px-3 py-1 text-xs font-semibold text-secondary-dark">
                    <ShieldCheck className="h-3 w-3" /> Verified
                  </span>
                ) : null}
              </div>
            </div>
          </div>

          <dl className="grid grid-cols-1 gap-5 py-8 sm:grid-cols-2">
            {details.map(({ icon: Icon, label, value }) => (
              <div key={label} className="flex items-start gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-muted text-muted-foreground">
                  <Icon className="h-4 w-4" />
                </span>
                <div className="flex flex-col">
                  <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
                  <dd className="text-sm font-medium text-foreground">{value}</dd>
                </div>
              </div>
            ))}
          </dl>

          <div className="border-t border-border pt-6">
            <Button variant="outline" size="md" onClick={() => logout()} className="gap-2">
              <LogOut className="h-4 w-4" />
              Log Out
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ProfilePage() {
  return (
    <ProtectedRoute>
      <ProfileContent />
    </ProtectedRoute>
  );
}
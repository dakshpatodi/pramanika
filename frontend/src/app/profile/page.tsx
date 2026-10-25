"use client";

import { CalendarDays, Clock, LogOut, ShieldCheck } from "lucide-react";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { ProfileForm } from "@/components/dashboard/ProfileForm";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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

  const facts = [
    { icon: CalendarDays, label: "Member since", value: formatDate(user.created_at) },
    { icon: Clock, label: "Last login", value: formatDate(user.last_login) },
  ];

  return (
    <DashboardShell title="Profile" description="See and update the details on your account.">
      <div className="flex max-w-2xl flex-col gap-6">
        <Card className="p-6">
          <div className="flex flex-col items-center gap-4 text-center sm:flex-row sm:text-left">
            <span className="flex h-20 w-20 shrink-0 items-center justify-center rounded-blob bg-primary text-2xl font-semibold text-primary-foreground">
              {initials}
            </span>
            <div className="flex flex-col gap-2">
              <p className="font-display text-2xl font-semibold text-foreground">{fullName}</p>
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

          <dl className="mt-6 grid grid-cols-1 gap-5 border-t border-border pt-6 sm:grid-cols-2">
            {facts.map(({ icon: Icon, label, value }) => (
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
        </Card>

        <Card className="p-6">
          <h2 className="mb-5 font-display text-xl font-semibold text-foreground">Edit details</h2>
          <ProfileForm />
        </Card>

        <div>
          <Button variant="outline" size="md" onClick={() => logout()} className="gap-2">
            <LogOut className="h-4 w-4" />
            Log Out
          </Button>
        </div>
      </div>
    </DashboardShell>
  );
}

export default function ProfilePage() {
  return (
    <ProtectedRoute>
      <ProfileContent />
    </ProtectedRoute>
  );
}

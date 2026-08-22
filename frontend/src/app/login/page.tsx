"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { AlertCircle, ArrowRight } from "lucide-react";

import { AuthCard } from "@/components/auth/AuthCard";
import { PasswordInput } from "@/components/auth/PasswordInput";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { getApiErrorMessage } from "@/lib/errors";
import { loginSchema, type LoginFormValues } from "@/lib/validations/auth";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuth();
  const [serverError, setServerError] = useState<string | null>(null);
  const [showForgotNote, setShowForgotNote] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "", rememberMe: true },
  });

  async function onSubmit(values: LoginFormValues) {
    setServerError(null);
    try {
      await login(values.email, values.password, values.rememberMe ?? true);
      // If ProtectedRoute redirected here from somewhere (e.g. /profile),
      // send the user back there instead of always landing on the
      // homepage - see components/auth/ProtectedRoute.tsx.
      const redirectTo = searchParams.get("redirect") ?? "/";
      router.push(redirectTo);
    } catch (error) {
      setServerError(getApiErrorMessage(error, "Unable to log in. Please try again."));
    }
  }

  return (
    <AuthCard
      title="Welcome back"
      subtitle="Log in to your Pramanika account to continue."
      footer={
        <>
          Don&apos;t have an account?{" "}
          <Link href="/register" className="font-medium text-primary hover:underline">
            Create one
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-5">
        {serverError ? (
          <div className="flex items-start gap-2 rounded-xl bg-accent/10 p-3 text-sm text-accent-dark" role="alert">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{serverError}</span>
          </div>
        ) : null}

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            invalid={!!errors.email}
            {...register("email")}
          />
          {errors.email ? <p className="text-sm text-accent">{errors.email.message}</p> : null}
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Password</Label>
            <button
              type="button"
              onClick={() => setShowForgotNote((current) => !current)}
              className="text-xs font-medium text-primary hover:underline"
            >
              Forgot password?
            </button>
          </div>
          <PasswordInput
            id="password"
            autoComplete="current-password"
            placeholder="••••••••"
            invalid={!!errors.password}
            {...register("password")}
          />
          {errors.password ? <p className="text-sm text-accent">{errors.password.message}</p> : null}
          {showForgotNote ? (
            <p className="text-xs text-muted-foreground">
              Password reset isn&apos;t available yet - please contact support in the meantime.
            </p>
          ) : null}
        </div>

        <label className="flex items-center gap-2 text-sm text-foreground">
          <Checkbox {...register("rememberMe")} />
          Remember me
        </label>

        <Button type="submit" size="lg" disabled={isSubmitting} className="w-full">
          {isSubmitting ? (
            "Logging in..."
          ) : (
            <>
              Log In <ArrowRight className="h-4 w-4" />
            </>
          )}
        </Button>
      </form>
    </AuthCard>
  );
}

function LoginFormFallback() {
  return (
    <AuthCard title="Welcome back" subtitle="Log in to your Pramanika account to continue.">
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-border border-t-primary" />
      </div>
    </AuthCard>
  );
}

export default function LoginPage() {
  // useSearchParams() requires a Suspense boundary in the App Router -
  // without it, Next.js bails the ENTIRE route out of static rendering
  // and warns at build time. Splitting the form into its own component
  // lets this fallback render instantly while the real form (and its
  // dependency on the URL's search params) streams in.
  return (
    <Suspense fallback={<LoginFormFallback />}>
      <LoginForm />
    </Suspense>
  );
}
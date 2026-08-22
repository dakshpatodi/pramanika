"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { AlertCircle, CheckCircle2 } from "lucide-react";

import { AuthCard } from "@/components/auth/AuthCard";
import { PasswordInput } from "@/components/auth/PasswordInput";
import { PasswordStrengthHints } from "@/components/auth/PasswordStrengthHints";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { getApiErrorMessage } from "@/lib/errors";
import { registerSchema, type RegisterFormValues } from "@/lib/validations/auth";

export default function RegisterPage() {
  const router = useRouter();
  const { register: registerUser } = useAuth();
  const [serverError, setServerError] = useState<string | null>(null);
  const [registered, setRegistered] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      first_name: "",
      last_name: "",
      email: "",
      phone_number: "",
      password: "",
      confirm_password: "",
      accept_terms: false,
    },
  });

  const passwordValue = watch("password");

  async function onSubmit(values: RegisterFormValues) {
    setServerError(null);
    try {
      // accept_terms is a frontend-only field - the backend's
      // UserCreate schema deliberately has no such field (see
      // Milestone 3 notes), so it's stripped before the request is sent.
      const { accept_terms: _acceptTerms, ...payload } = values;
      await registerUser(payload);
      setRegistered(true);
      setTimeout(() => router.push("/login"), 2500);
    } catch (error) {
      setServerError(getApiErrorMessage(error, "Unable to create your account. Please try again."));
    }
  }

  if (registered) {
    return (
      <AuthCard title="Account created">
        <div className="flex flex-col items-center gap-3 py-4 text-center">
          <span className="flex h-14 w-14 items-center justify-center rounded-blob bg-primary-light text-primary">
            <CheckCircle2 className="h-7 w-7" />
          </span>
          <p className="text-sm text-muted-foreground">Your account is ready. Redirecting you to log in...</p>
          <Link href="/login" className="text-sm font-medium text-primary hover:underline">
            Go to login now
          </Link>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Create your account"
      subtitle="Join Pramanika for fresh cereals, millets, and pantry staples."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-primary hover:underline">
            Log in
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

        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="first_name">First name</Label>
            <Input
              id="first_name"
              autoComplete="given-name"
              invalid={!!errors.first_name}
              {...register("first_name")}
            />
            {errors.first_name ? <p className="text-sm text-accent">{errors.first_name.message}</p> : null}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="last_name">Last name</Label>
            <Input id="last_name" autoComplete="family-name" invalid={!!errors.last_name} {...register("last_name")} />
            {errors.last_name ? <p className="text-sm text-accent">{errors.last_name.message}</p> : null}
          </div>
        </div>

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
          <Label htmlFor="phone_number">Phone number</Label>
          <Input
            id="phone_number"
            type="tel"
            autoComplete="tel"
            placeholder="+919876543210"
            invalid={!!errors.phone_number}
            {...register("phone_number")}
          />
          {errors.phone_number ? <p className="text-sm text-accent">{errors.phone_number.message}</p> : null}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Password</Label>
          <PasswordInput
            id="password"
            autoComplete="new-password"
            placeholder="••••••••"
            invalid={!!errors.password}
            {...register("password")}
          />
          <PasswordStrengthHints password={passwordValue} />
          {errors.password ? <p className="text-sm text-accent">{errors.password.message}</p> : null}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="confirm_password">Confirm password</Label>
          <PasswordInput
            id="confirm_password"
            autoComplete="new-password"
            placeholder="••••••••"
            invalid={!!errors.confirm_password}
            {...register("confirm_password")}
          />
          {errors.confirm_password ? <p className="text-sm text-accent">{errors.confirm_password.message}</p> : null}
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="flex items-start gap-2 text-sm text-foreground">
            <Checkbox className="mt-0.5" {...register("accept_terms")} />
            <span>I agree to the Terms of Service and Privacy Policy.</span>
          </label>
          {errors.accept_terms ? <p className="text-sm text-accent">{errors.accept_terms.message}</p> : null}
        </div>

        <Button type="submit" size="lg" disabled={isSubmitting} className="w-full">
          {isSubmitting ? "Creating account..." : "Create Account"}
        </Button>
      </form>
    </AuthCard>
  );
}
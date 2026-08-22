import { Check, X } from "lucide-react";

import { cn } from "@/lib/utils";

interface PasswordStrengthHintsProps {
  password: string;
}

// Mirrors backend/app/schemas/user.py's _validate_password_strength and
// lib/validations/auth.ts's registerSchema exactly - keep all three in
// sync if the rules ever change.
const rules = [
  { label: "At least 8 characters", test: (value: string) => value.length >= 8 },
  { label: "One uppercase letter", test: (value: string) => /[A-Z]/.test(value) },
  { label: "One lowercase letter", test: (value: string) => /[a-z]/.test(value) },
  { label: "One digit", test: (value: string) => /\d/.test(value) },
  { label: "One special character", test: (value: string) => /[^A-Za-z0-9]/.test(value) },
];

/** Live checklist shown under the password field on /register, so a user
 * finds out which rule they're missing before submitting, rather than
 * from a single generic error message after the fact. */
export function PasswordStrengthHints({ password }: PasswordStrengthHintsProps) {
  if (!password) return null;

  return (
    <ul className="grid grid-cols-1 gap-1 pt-1 sm:grid-cols-2">
      {rules.map((rule) => {
        const met = rule.test(password);
        return (
          <li
            key={rule.label}
            className={cn("flex items-center gap-1.5 text-xs", met ? "text-primary" : "text-muted-foreground")}
          >
            {met ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
            {rule.label}
          </li>
        );
      })}
    </ul>
  );
}
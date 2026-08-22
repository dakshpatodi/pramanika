import { z } from "zod";

// Matches backend/app/schemas/user.py's _PHONE_PATTERN exactly.
const phoneRegex = /^\+?[1-9]\d{6,14}$/;

export const loginSchema = z.object({
  email: z.string().min(1, "Email is required.").email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
  rememberMe: z.boolean().optional(),
});

export type LoginFormValues = z.infer<typeof loginSchema>;

export const registerSchema = z
  .object({
    first_name: z.string().min(1, "First name is required.").max(100, "First name is too long."),
    last_name: z.string().min(1, "Last name is required.").max(100, "Last name is too long."),
    email: z.string().min(1, "Email is required.").email("Enter a valid email address."),
    phone_number: z
      .string()
      .min(1, "Phone number is required.")
      .regex(phoneRegex, "Enter a valid phone number, e.g. +919876543210."),
    // These four .regex() rules mirror UserCreate._validate_password_strength
    // in backend/app/schemas/user.py exactly - if that ever changes, update
    // both PasswordStrengthHints.tsx and this schema to match.
    password: z
      .string()
      .min(8, "Password must be at least 8 characters.")
      .max(72, "Password must be at most 72 characters.")
      .regex(/[A-Z]/, "Password must contain at least one uppercase letter.")
      .regex(/[a-z]/, "Password must contain at least one lowercase letter.")
      .regex(/\d/, "Password must contain at least one digit.")
      .regex(/[^A-Za-z0-9]/, "Password must contain at least one special character."),
    confirm_password: z.string().min(1, "Please confirm your password."),
    accept_terms: z.boolean().refine((value) => value === true, {
      message: "You must accept the terms to continue.",
    }),
  })
  .refine((data) => data.password === data.confirm_password, {
    message: "Passwords do not match.",
    path: ["confirm_password"],
  });

export type RegisterFormValues = z.infer<typeof registerSchema>;
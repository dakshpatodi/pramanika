import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge conditional class names and resolve conflicting Tailwind
 * utility classes (e.g. "p-2" vs "p-4") in favor of the last one.
 * Used throughout components/ui and layout components.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Formats a number as INR currency, e.g. 249 -> "₹249". */
export function formatPrice(amount: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}

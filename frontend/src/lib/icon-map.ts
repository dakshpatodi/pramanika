import {
  BadgeCheck,
  Bean,
  CookingPot,
  Cookie,
  FlaskConical,
  HeartPulse,
  Leaf,
  Nut,
  Sprout,
  Truck,
  Wheat,
  type LucideIcon,
} from "lucide-react";

/**
 * Maps the plain-string icon names stored in placeholder data (and,
 * eventually, in the API response) to an actual lucide-react component.
 * Keeping this in one place means data files never import React directly.
 */
export const iconMap: Record<string, LucideIcon> = {
  Wheat,
  CookingPot,
  Sprout,
  Bean,
  Nut,
  FlaskConical,
  Cookie,
  Leaf,
  Truck,
  HeartPulse,
  BadgeCheck,
};

/**
 * Phase 1 has no product photography yet, so each product's `image` key
 * (see lib/placeholder-data.ts) resolves to a representative icon instead.
 * Swap ProductCard's image block for a real <Image> once photos exist.
 */
export const productPlaceholderIconMap: Record<string, LucideIcon> = {
  oats: Wheat,
  mix: CookingPot,
  millet: Sprout,
  flour: Wheat,
  pulses: Bean,
  nuts: Nut,
  spice: FlaskConical,
  snack: Cookie,
};

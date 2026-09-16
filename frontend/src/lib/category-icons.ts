/**
 * Maps a category slug to a representative icon, for use as a
 * placeholder visual on product/category cards until real photography
 * exists (same situation Phase 1's homepage placeholders were in).
 *
 * Falls back to a generic Package icon for any category not in this
 * map, so a newly-added category never breaks rendering - it just gets
 * a slightly less specific icon until this map is updated.
 */

import { CookingPot, Cookie, HeartPulse, Nut, Package, Wheat, type LucideIcon } from "lucide-react";

const categoryIconMap: Record<string, LucideIcon> = {
  cereals: Wheat,
  "ready-mixes": CookingPot,
  "dry-fruits": Nut,
  snacks: Cookie,
  "health-foods": HeartPulse,
};

export function getCategoryIcon(slug: string): LucideIcon {
  return categoryIconMap[slug] ?? Package;
}
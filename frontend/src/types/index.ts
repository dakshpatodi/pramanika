/**
 * Shared UI types for Phase 1.
 *
 * These describe the *shape* of the placeholder content rendered on the
 * homepage today. They intentionally mirror what the real API will
 * eventually return, so swapping placeholder data for live API data in
 * Phase 2 requires no changes to the components that consume these types.
 */

export interface Category {
  id: string;
  name: string;
  slug: string;
  icon: string; // lucide-react icon name, resolved in CategoryCard
  productCount: number;
}

export interface Product {
  id: string;
  name: string;
  category: string;
  price: number;
  compareAtPrice?: number;
  rating: number; // 0-5
  reviewCount: number;
  image: string;
  badge?: "New" | "Bestseller" | "Sale";
}

export interface Feature {
  id: string;
  title: string;
  description: string;
  icon: string; // lucide-react icon name
}

export interface Testimonial {
  id: string;
  name: string;
  location: string;
  quote: string;
  rating: number; // 0-5
  initials: string;
}

import type { Category, Feature, Product, Testimonial } from "@/types";

/**
 * Static placeholder content for the Phase 1 homepage.
 * This will be replaced by real API calls (via src/services) once the
 * product catalog endpoints exist on the backend.
 */

export const categories: Category[] = [
  { id: "cat-1", name: "Cereals", slug: "cereals", icon: "Wheat", productCount: 24 },
  { id: "cat-2", name: "Ready Mixes", slug: "ready-mixes", icon: "CookingPot", productCount: 18 },
  { id: "cat-3", name: "Millets", slug: "millets", icon: "Sprout", productCount: 15 },
  { id: "cat-4", name: "Flours", slug: "flours", icon: "Wheat", productCount: 21 },
  { id: "cat-5", name: "Pulses", slug: "pulses", icon: "Bean", productCount: 19 },
  { id: "cat-6", name: "Dry Fruits", slug: "dry-fruits", icon: "Nut", productCount: 12 },
  { id: "cat-7", name: "Spices", slug: "spices", icon: "FlaskConical", productCount: 27 },
  { id: "cat-8", name: "Healthy Snacks", slug: "healthy-snacks", icon: "Cookie", productCount: 16 },
];

export const products: Product[] = [
  {
    id: "prod-1",
    name: "Rolled Oats Classic",
    category: "Cereals",
    price: 249,
    compareAtPrice: 299,
    rating: 4.6,
    reviewCount: 128,
    image: "oats",
    badge: "Bestseller",
  },
  {
    id: "prod-2",
    name: "Multi-Millet Dosa Mix",
    category: "Ready Mixes",
    price: 189,
    rating: 4.4,
    reviewCount: 76,
    image: "mix",
    badge: "New",
  },
  {
    id: "prod-3",
    name: "Foxtail Millet",
    category: "Millets",
    price: 159,
    compareAtPrice: 199,
    rating: 4.7,
    reviewCount: 94,
    image: "millet",
    badge: "Sale",
  },
  {
    id: "prod-4",
    name: "Whole Wheat Atta",
    category: "Flours",
    price: 329,
    rating: 4.5,
    reviewCount: 210,
    image: "flour",
  },
  {
    id: "prod-5",
    name: "Organic Moong Dal",
    category: "Pulses",
    price: 145,
    rating: 4.8,
    reviewCount: 152,
    image: "pulses",
    badge: "Bestseller",
  },
  {
    id: "prod-6",
    name: "Premium Almonds",
    category: "Dry Fruits",
    price: 599,
    compareAtPrice: 699,
    rating: 4.6,
    reviewCount: 88,
    image: "nuts",
    badge: "Sale",
  },
  {
    id: "prod-7",
    name: "Turmeric Powder",
    category: "Spices",
    price: 99,
    rating: 4.5,
    reviewCount: 63,
    image: "spice",
  },
  {
    id: "prod-8",
    name: "Roasted Makhana",
    category: "Healthy Snacks",
    price: 179,
    rating: 4.3,
    reviewCount: 41,
    image: "snack",
    badge: "New",
  },
];

export const features: Feature[] = [
  {
    id: "feat-1",
    title: "Fresh Products",
    description: "Sourced in small batches and packed close to harvest, never left sitting in a warehouse.",
    icon: "Leaf",
  },
  {
    id: "feat-2",
    title: "Fast Delivery",
    description: "Dispatched within 24 hours so your pantry staples arrive while they're still at their best.",
    icon: "Truck",
  },
  {
    id: "feat-3",
    title: "Healthy Choices",
    description: "No added preservatives or refined sugar - just whole grains, pulses, and real ingredients.",
    icon: "HeartPulse",
  },
  {
    id: "feat-4",
    title: "Premium Quality",
    description: "Every batch is lab-tested for purity before it ships, so quality never varies box to box.",
    icon: "BadgeCheck",
  },
];

export const testimonials: Testimonial[] = [
  {
    id: "test-1",
    name: "Ananya Rao",
    location: "Bengaluru",
    quote:
      "Switched our whole kitchen to Pramanika millets and flours. The freshness is obvious from the first bite.",
    rating: 5,
    initials: "AR",
  },
  {
    id: "test-2",
    name: "Vikram Sethi",
    location: "Pune",
    quote:
      "The ready mixes make weekday breakfasts so much easier, and my kids still think it's a treat.",
    rating: 5,
    initials: "VS",
  },
  {
    id: "test-3",
    name: "Meera Nair",
    location: "Kochi",
    quote:
      "Consistent quality every single order. The dry fruits especially taste noticeably fresher than the supermarket brands.",
    rating: 4,
    initials: "MN",
  },
];

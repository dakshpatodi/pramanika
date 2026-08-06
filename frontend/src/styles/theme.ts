/**
 * Brand tokens mirrored from tailwind.config.ts.
 *
 * Prefer Tailwind utility classes (bg-primary, text-accent, etc.) for
 * styling components. Reach for these raw values only where a class name
 * won't work - e.g. an inline SVG `fill`, or a charting library that
 * takes hex strings directly.
 */
export const brandColors = {
  primary: "#3E7D32",
  primaryDark: "#2E5D25",
  secondary: "#F4B400",
  accent: "#FF7043",
  background: "#FBFAF6",
  foreground: "#1E2A1A",
  muted: "#F2EFE6",
  border: "#E4DFD1",
} as const;

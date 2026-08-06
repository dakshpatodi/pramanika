"use client";

import { useEffect, useState } from "react";

/**
 * Tracks whether a CSS media query currently matches.
 * Purely a UI utility (e.g. toggling the mobile nav) - no business logic.
 *
 * Example: const isDesktop = useMediaQuery("(min-width: 1024px)");
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const mediaQueryList = window.matchMedia(query);
    setMatches(mediaQueryList.matches);

    const listener = (event: MediaQueryListEvent) => setMatches(event.matches);
    mediaQueryList.addEventListener("change", listener);

    return () => mediaQueryList.removeEventListener("change", listener);
  }, [query]);

  return matches;
}

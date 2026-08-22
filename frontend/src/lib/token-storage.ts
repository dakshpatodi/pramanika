/**
 * Thin wrapper around browser storage for the two auth tokens.
 *
 * Centralized in one file so the storage mechanism can change later
 * (e.g. to httpOnly cookies for better XSS protection) without touching
 * every place that reads/writes a token.
 *
 * "Remember me" is implemented as a real choice between the two Web
 * Storage APIs, not just a decorative checkbox: `persist: true` uses
 * localStorage (survives closing the browser), `persist: false` uses
 * sessionStorage (cleared the moment the tab/browser closes).
 */

const ACCESS_TOKEN_KEY = "pramanika_access_token";
const REFRESH_TOKEN_KEY = "pramanika_refresh_token";

function getStorage(area: "local" | "session"): Storage | null {
  if (typeof window === "undefined") return null;
  return area === "local" ? window.localStorage : window.sessionStorage;
}

export const tokenStorage = {
  setTokens(accessToken: string, refreshToken: string, persist: boolean = true): void {
    // Clear both areas first so a token never ends up living in both at
    // once - e.g. someone logs in with "remember me" on, then later logs
    // in again with it off, on the same browser.
    this.clearTokens();
    const storage = getStorage(persist ? "local" : "session");
    storage?.setItem(ACCESS_TOKEN_KEY, accessToken);
    storage?.setItem(REFRESH_TOKEN_KEY, refreshToken);
  },

  getAccessToken(): string | null {
    return (
      getStorage("local")?.getItem(ACCESS_TOKEN_KEY) ?? getStorage("session")?.getItem(ACCESS_TOKEN_KEY) ?? null
    );
  },

  getRefreshToken(): string | null {
    return (
      getStorage("local")?.getItem(REFRESH_TOKEN_KEY) ?? getStorage("session")?.getItem(REFRESH_TOKEN_KEY) ?? null
    );
  },

  /** True if the current session was stored via "Remember me" (localStorage)
   * rather than session-only (sessionStorage). Used when a silent token
   * refresh happens, so the new tokens land back in the same storage
   * area instead of the refresh flow silently resetting that choice. */
  isPersisted(): boolean {
    return getStorage("local")?.getItem(REFRESH_TOKEN_KEY) != null;
  },

  clearTokens(): void {
    getStorage("local")?.removeItem(ACCESS_TOKEN_KEY);
    getStorage("local")?.removeItem(REFRESH_TOKEN_KEY);
    getStorage("session")?.removeItem(ACCESS_TOKEN_KEY);
    getStorage("session")?.removeItem(REFRESH_TOKEN_KEY);
  },
};
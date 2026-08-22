/**
 * Minimal pub/sub for one specific signal: "the refresh token is dead,
 * force a full logout."
 *
 * Exists to solve a layering problem: the Axios response interceptor
 * (lib/axios.ts) is what discovers a refresh token has failed, but it
 * has no business importing React or AuthContext directly - it's a
 * plain HTTP client, not a component. AuthContext is the one place that
 * actually owns `user` state and can redirect. A browser CustomEvent is
 * a clean way to let the former notify the latter without either
 * importing the other.
 */

export const AUTH_LOGOUT_EVENT = "pramanika:auth:force-logout";

export function emitForceLogout(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(AUTH_LOGOUT_EVENT));
  }
}

/** Returns an unsubscribe function, ready to hand straight to a useEffect cleanup. */
export function onForceLogout(handler: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(AUTH_LOGOUT_EVENT, handler);
  return () => window.removeEventListener(AUTH_LOGOUT_EVENT, handler);
}
/**
 * Where to send a user after login when the address asks for `?redirect=...`.
 *
 * That value comes from the address bar, so anyone can put anything in it (a link in an email, a
 * look-alike page). Only a path INSIDE this site is followed; everything else falls back to the home
 * page, so a login link can never bounce a freshly signed-in user to another website.
 */
export function safeRedirectPath(value: string | null | undefined, fallback = "/"): string {
  if (typeof value !== "string" || value === "") return fallback;
  // Must be an absolute path on this site: "/x", never "x", "//host", "/\host", "https://host", "javascript:..."
  if (value[0] !== "/" || value[1] === "/" || value[1] === "\\") return fallback;
  // No backslashes, control characters or whitespace tricks anywhere (browsers normalise some of these to "//").
  if (/[\\\u0000-\u001f\u007f\s]/.test(value)) return fallback;
  // Belt and braces: resolved against a dummy origin it must still be on that origin.
  try {
    const base = "http://pramanika.invalid";
    const resolved = new URL(value, base);
    if (resolved.origin !== base) return fallback;
  } catch {
    return fallback;
  }
  return value;
}

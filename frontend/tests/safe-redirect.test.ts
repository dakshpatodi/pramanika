import { describe, expect, it } from "vitest";

import { safeRedirectPath } from "@/lib/safe-redirect";

describe("safeRedirectPath", () => {
  it.each(["/", "/profile", "/shop/muesli", "/admin/orders?status=paid", "/orders/1#top", "/shop?category=a%2Fb"])("keeps the site path %s", (path) => {
    expect(safeRedirectPath(path)).toBe(path);
  });

  it.each([
    "https://evil.example",
    "http://evil.example/login",
    "//evil.example",
    "///evil.example",
    "/\\evil.example",
    "\\\\evil.example",
    "\\/evil.example",
    "javascript:alert(1)",
    "data:text/html,hi",
    "evil.example/path",
    "profile",
    "/ /evil.example",
    "/\t/evil.example",
    "/\n/evil.example",
    "/%0a/evil.example".replace("%0a", "\n"),
    "/a\\b",
    " /profile",
    "/\u0000x",
  ])("falls back for %j", (value) => {
    expect(safeRedirectPath(value)).toBe("/");
  });

  it("falls back for a missing or empty value, and honours a custom fallback", () => {
    expect(safeRedirectPath(null)).toBe("/");
    expect(safeRedirectPath(undefined)).toBe("/");
    expect(safeRedirectPath("")).toBe("/");
    expect(safeRedirectPath("https://evil.example", "/account")).toBe("/account");
  });
});

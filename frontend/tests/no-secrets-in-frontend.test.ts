import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Phase 7: the browser only ever learns the PUBLIC Razorpay key id, and it
 * learns it from the server's reply. No secret, no webhook secret, and no
 * key of any kind belongs in the frontend source.
 */
// `npm test` runs from the frontend root
const SRC = resolve(process.cwd(), "src");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx|js|jsx|json|css)$/.test(name) ? [path] : [];
  });
}

const files = sourceFiles(SRC).map((path) => ({ path: path.slice(SRC.length + 1), text: readFileSync(path, "utf8") }));

describe("frontend source holds no Razorpay secret", () => {
  it("scans a real set of files", () => {
    expect(files.length).toBeGreaterThan(20);
    expect(files.some((f) => f.path.includes("usePayment"))).toBe(true);
  });

  it.each([
    ["the key secret's name", /RAZORPAY_KEY_SECRET|key_secret/i],
    ["the webhook secret's name", /RAZORPAY_WEBHOOK_SECRET|webhook_secret/i],
    ["a public env var that holds a secret", /NEXT_PUBLIC_\w*(SECRET|PASSWORD)/i],
    ["a Razorpay key written into the code", /rzp_(live|test)_(?!x+\b)[A-Za-z0-9]{8,}/],
    ["a live-mode key prefix", /rzp_live_/],
  ])("never contains %s", (_label, pattern) => {
    const hits = files.filter((f) => pattern.test(f.text)).map((f) => f.path);
    expect(hits).toEqual([]);
  });

  it("does not even read the key id from the environment: it comes from the server's reply", () => {
    const hits = files.filter((f) => /process\.env\.\w*RAZORPAY/i.test(f.text)).map((f) => f.path);
    expect(hits).toEqual([]);
  });

  it("never sends an amount to the backend when starting a payment", () => {
    const service = files.find((f) => f.path.replace(/\\/g, "/").endsWith("services/payments.ts"));
    expect(service).toBeDefined();
    expect(service!.text).not.toMatch(/\bamount\w*\s*:/);
    const create = service!.text.slice(service!.text.indexOf("function createPayment"), service!.text.indexOf("function verifyPayment"));
    expect(create).toMatch(/\.post<[^(]*\(`[^`]*`\)/); // the URL and nothing else: no body
  });
});

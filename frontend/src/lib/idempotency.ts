/**
 * Idempotency keys for checkout.
 *
 * The rule the backend enforces: the same key + the same request body
 * returns the original order; the same key + a DIFFERENT body is a 409.
 * So a key must live exactly as long as the request it names:
 *
 *   - retrying the same request (network error, timeout, double click,
 *     "Try again") -> the SAME key, so a request that actually reached the
 *     server can never become a second order;
 *   - the request changed (other address, other total) -> a NEW key;
 *   - the order was placed -> forget the key, the next checkout is new.
 *
 * A request that FAILED with a clear answer (out of stock, bad coupon...)
 * stored nothing on the server, so reusing its key for the same body later
 * is still correct.
 */

import type { PlaceOrderInput } from "@/types/order";

/** 8-64 characters of letters, digits, "." "_" ":" "-" (the server's rule). */
const KEY_PATTERN = /^[A-Za-z0-9._:-]{8,64}$/;

export function newIdempotencyKey(): string {
  const uuid =
    typeof globalThis.crypto !== "undefined" && typeof globalThis.crypto.randomUUID === "function"
      ? globalThis.crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}-${Math.random().toString(36).slice(2, 12)}`;
  return `chk-${uuid}`;
}

export function isValidIdempotencyKey(key: string): boolean {
  return KEY_PATTERN.test(key);
}

/** Money as the server compares it: two decimals, so 259 and 259.0 and
 * 258.99999999 (float noise) are all the same request. */
export function normaliseTotal(total: number | undefined): number | undefined {
  if (total === undefined) return undefined;
  return Math.round(total * 100) / 100;
}

/** Stable identity of a checkout request body. */
export function requestFingerprint(input: PlaceOrderInput): string {
  return JSON.stringify([input.shipping_address_id, normaliseTotal(input.expected_total) ?? null]);
}

export interface IdempotencyKeyStore {
  /** The key for this request: the current one if the request is unchanged, a fresh one if it changed. */
  keyFor(input: PlaceOrderInput): string;
  /** Forget the current key (call after the order was placed). */
  reset(): void;
}

export function createIdempotencyKeyStore(): IdempotencyKeyStore {
  let current: { fingerprint: string; key: string } | null = null;
  return {
    keyFor(input) {
      const fingerprint = requestFingerprint(input);
      if (current === null || current.fingerprint !== fingerprint) {
        current = { fingerprint, key: newIdempotencyKey() };
      }
      return current.key;
    },
    reset() {
      current = null;
    },
  };
}
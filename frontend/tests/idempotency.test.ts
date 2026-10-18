import { describe, expect, it } from "vitest";

import {
  createIdempotencyKeyStore,
  isValidIdempotencyKey,
  newIdempotencyKey,
  normaliseTotal,
  requestFingerprint,
} from "@/lib/idempotency";

describe("newIdempotencyKey", () => {
  it("produces keys the server accepts (8-64 chars, allowed characters)", () => {
    for (let i = 0; i < 50; i++) expect(isValidIdempotencyKey(newIdempotencyKey())).toBe(true);
  });

  it("produces different keys each time", () => {
    const keys = new Set(Array.from({ length: 200 }, newIdempotencyKey));
    expect(keys.size).toBe(200);
  });

  it("still produces a valid key when crypto.randomUUID is unavailable", () => {
    const original = globalThis.crypto.randomUUID;
    // @ts-expect-error simulating an old browser
    globalThis.crypto.randomUUID = undefined;
    try {
      const key = newIdempotencyKey();
      expect(isValidIdempotencyKey(key)).toBe(true);
    } finally {
      globalThis.crypto.randomUUID = original;
    }
  });
});

describe("isValidIdempotencyKey", () => {
  it("mirrors the server rule", () => {
    expect(isValidIdempotencyKey("abcdefgh")).toBe(true);
    expect(isValidIdempotencyKey("a.b_c:d-e1")).toBe(true);
    expect(isValidIdempotencyKey("short")).toBe(false);
    expect(isValidIdempotencyKey("x".repeat(65))).toBe(false);
    expect(isValidIdempotencyKey("x".repeat(64))).toBe(true);
    expect(isValidIdempotencyKey("has space 12345")).toBe(false);
  });
});

describe("normaliseTotal / requestFingerprint", () => {
  it("rounds float noise to two decimals and leaves undefined alone", () => {
    expect(normaliseTotal(258.99999999)).toBe(259);
    expect(normaliseTotal(416.5)).toBe(416.5);
    expect(normaliseTotal(undefined)).toBeUndefined();
  });

  it("treats the same address and the same money as the same request", () => {
    const a = requestFingerprint({ shipping_address_id: "a1", expected_total: 259 });
    const b = requestFingerprint({ shipping_address_id: "a1", expected_total: 258.99999999 });
    expect(a).toBe(b);
  });

  it("tells different addresses, totals, and missing totals apart", () => {
    const base = requestFingerprint({ shipping_address_id: "a1", expected_total: 259 });
    expect(requestFingerprint({ shipping_address_id: "a2", expected_total: 259 })).not.toBe(base);
    expect(requestFingerprint({ shipping_address_id: "a1", expected_total: 260 })).not.toBe(base);
    expect(requestFingerprint({ shipping_address_id: "a1" })).not.toBe(base);
  });
});

describe("createIdempotencyKeyStore", () => {
  const request = { shipping_address_id: "a1", expected_total: 259 };

  it("gives the same key to a repeated identical request", () => {
    const store = createIdempotencyKeyStore();
    expect(store.keyFor(request)).toBe(store.keyFor({ ...request }));
  });

  it("gives a new key when the address or the total changes", () => {
    const store = createIdempotencyKeyStore();
    const first = store.keyFor(request);
    const otherAddress = store.keyFor({ ...request, shipping_address_id: "a2" });
    const otherTotal = store.keyFor({ ...request, shipping_address_id: "a2", expected_total: 300 });
    expect(new Set([first, otherAddress, otherTotal]).size).toBe(3);
  });

  it("gives a new key after reset (the order was placed)", () => {
    const store = createIdempotencyKeyStore();
    const first = store.keyFor(request);
    store.reset();
    expect(store.keyFor(request)).not.toBe(first);
  });

  it("separate stores never share keys", () => {
    expect(createIdempotencyKeyStore().keyFor(request)).not.toBe(createIdempotencyKeyStore().keyFor(request));
  });
});
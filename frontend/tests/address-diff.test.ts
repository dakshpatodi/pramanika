import { describe, expect, it } from "vitest";

import { MAX_ADDRESSES, diffAddress } from "@/lib/address-validation";
import type { Address, AddressInput } from "@/types/address";

const saved: Address = {
  id: "a1", full_name: "Asha Rao", phone_number: "9876543210", address_line_1: "12 MG Road", address_line_2: "Flat 4",
  city: "Pune", state: "Maharashtra", postal_code: "411001", country: "India", is_default: true, created_at: "2026-10-05T00:00:00Z",
};
const same: AddressInput = {
  full_name: "Asha Rao", phone_number: "9876543210", address_line_1: "12 MG Road", address_line_2: "Flat 4",
  city: "Pune", state: "Maharashtra", postal_code: "411001",
};

describe("diffAddress", () => {
  it("is empty when nothing changed, including whitespace-only edits", () => {
    expect(diffAddress(saved, same)).toEqual({});
    expect(diffAddress(saved, { ...same, city: "  Pune  ", address_line_2: " Flat 4 " })).toEqual({});
  });

  it("carries only the fields that changed, trimmed", () => {
    expect(diffAddress(saved, { ...same, city: " Mumbai " })).toEqual({ city: "Mumbai" });
    expect(diffAddress(saved, { ...same, postal_code: "400001", phone_number: "+919811122233" })).toEqual({
      postal_code: "400001",
      phone_number: "+919811122233",
    });
  });

  it("clears the optional second line with null, and sets it when it was empty", () => {
    expect(diffAddress(saved, { ...same, address_line_2: "" })).toEqual({ address_line_2: null });
    expect(diffAddress(saved, { ...same, address_line_2: "   " })).toEqual({ address_line_2: null });
    expect(diffAddress({ ...saved, address_line_2: null }, { ...same, address_line_2: "" })).toEqual({});
    expect(diffAddress({ ...saved, address_line_2: null }, { ...same, address_line_2: "Gate 2" })).toEqual({ address_line_2: "Gate 2" });
  });

  it("never carries the default flag, the id or the country", () => {
    const keys = Object.keys(diffAddress(saved, { ...same, is_default: false, city: "X" } as AddressInput));
    expect(keys).toEqual(["city"]);
  });
});

describe("MAX_ADDRESSES", () => {
  it("matches the server's per-account limit of 20", () => {
    expect(MAX_ADDRESSES).toBe(20);
  });
});

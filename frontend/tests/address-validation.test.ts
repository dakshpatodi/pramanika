import { describe, expect, it } from "vitest";

import { toAddressInput, validateAddress } from "@/lib/address-validation";

const good = {
  full_name: "Asha Rao", phone_number: "9876543210", address_line_1: "12 MG Road", address_line_2: "",
  city: "Pune", state: "Maharashtra", postal_code: "411001",
};

describe("validateAddress", () => {
  it("accepts a good address", () => {
    expect(validateAddress(good)).toEqual({});
  });

  it("accepts a +country-code phone number and an optional second line", () => {
    expect(validateAddress({ ...good, phone_number: "+919876543210", address_line_2: "Flat 4" })).toEqual({});
  });

  it("requires a six-digit PIN that does not start with 0 (mirrors the server)", () => {
    for (const bad of ["", "41100", "4110011", "011001", "41100a", "411 001", "٤١١٠٠١"]) {
      expect(validateAddress({ ...good, postal_code: bad }).postal_code, `PIN ${JSON.stringify(bad)}`).toBeTruthy();
    }
    for (const ok of ["411001", "110001", "999999"]) {
      expect(validateAddress({ ...good, postal_code: ok }).postal_code, `PIN ${ok}`).toBeUndefined();
    }
  });

  it("applies the same phone rule as registration", () => {
    for (const bad of ["abc", "0123456789", "12345", "98765 43210", "+0123456789", "1".repeat(16)]) {
      expect(validateAddress({ ...good, phone_number: bad }).phone_number, `phone ${bad}`).toBeTruthy();
    }
    for (const ok of ["9876543210", "+919876543210", "1234567", "+".concat("1".repeat(15))]) {
      expect(validateAddress({ ...good, phone_number: ok }).phone_number, `phone ${ok}`).toBeUndefined();
    }
  });

  it("requires name, street, city and state - whitespace does not count", () => {
    const errors = validateAddress({ ...good, full_name: "  ", address_line_1: "", city: " ", state: "\t" });
    expect(Object.keys(errors).sort()).toEqual(["address_line_1", "city", "full_name", "state"]);
  });

  it("enforces the server's length limits", () => {
    expect(validateAddress({ ...good, full_name: "x".repeat(151) }).full_name).toBeTruthy();
    expect(validateAddress({ ...good, full_name: "x".repeat(150) }).full_name).toBeUndefined();
    expect(validateAddress({ ...good, address_line_1: "x".repeat(256) }).address_line_1).toBeTruthy();
    expect(validateAddress({ ...good, address_line_2: "x".repeat(256) }).address_line_2).toBeTruthy();
    expect(validateAddress({ ...good, city: "x".repeat(101) }).city).toBeTruthy();
  });
});

describe("toAddressInput", () => {
  it("trims every field and turns an empty second line into null", () => {
    expect(
      toAddressInput(
        { full_name: " Asha ", phone_number: " 9876543210 ", address_line_1: " 1 MG ", address_line_2: "   ", city: " Pune ", state: " MH ", postal_code: " 411001 " },
        false
      )
    ).toEqual({
      full_name: "Asha", phone_number: "9876543210", address_line_1: "1 MG", address_line_2: null,
      city: "Pune", state: "MH", postal_code: "411001", is_default: false,
    });
  });

  it("keeps a real second line and the default flag", () => {
    const input = toAddressInput({ ...good, address_line_2: " Flat 4 " }, true);
    expect(input.address_line_2).toBe("Flat 4");
    expect(input.is_default).toBe(true);
  });
});

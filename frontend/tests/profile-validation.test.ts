import { describe, expect, it } from "vitest";

import { NAME_MAX_LENGTH, changedFields, validateProfile, valuesFromUser } from "@/lib/profile-validation";

const saved = { first_name: "Asha", last_name: "Rao", phone_number: "+919876543210" };

describe("validateProfile", () => {
  it("accepts a normal profile", () => {
    expect(validateProfile(saved)).toEqual({});
    expect(validateProfile({ ...saved, phone_number: "9876543210" })).toEqual({});
  });

  it("requires every field and treats spaces as empty", () => {
    const errors = validateProfile({ first_name: "  ", last_name: "", phone_number: " " });
    expect(Object.keys(errors).sort()).toEqual(["first_name", "last_name", "phone_number"]);
  });

  it("applies the same phone rule as registration and addresses", () => {
    for (const ok of ["9876543210", "+919876543210", "1234567"]) {
      expect(validateProfile({ ...saved, phone_number: ok }).phone_number).toBeUndefined();
    }
    for (const bad of ["abc", "0123456789", "12345", "98765 43210", "+0123456789", "1".repeat(16)]) {
      expect(validateProfile({ ...saved, phone_number: bad }).phone_number, bad).toBeDefined();
    }
  });

  it("limits names to the server's 100 characters, counted after trimming", () => {
    expect(validateProfile({ ...saved, first_name: ` ${"x".repeat(NAME_MAX_LENGTH)} ` }).first_name).toBeUndefined();
    expect(validateProfile({ ...saved, first_name: "x".repeat(NAME_MAX_LENGTH + 1) }).first_name).toBeDefined();
    expect(validateProfile({ ...saved, last_name: "x".repeat(NAME_MAX_LENGTH + 1) }).last_name).toBeDefined();
  });
});

describe("changedFields", () => {
  it("is empty when nothing differs, even if only whitespace was added", () => {
    expect(changedFields(saved, saved)).toEqual({});
    expect(changedFields(saved, { ...saved, first_name: "  Asha  " })).toEqual({});
  });

  it("carries only the fields that changed, trimmed", () => {
    expect(changedFields(saved, { ...saved, first_name: "  Meera " })).toEqual({ first_name: "Meera" });
    expect(changedFields(saved, { first_name: "Meera", last_name: "Iyer", phone_number: "+919811122233" })).toEqual({
      first_name: "Meera",
      last_name: "Iyer",
      phone_number: "+919811122233",
    });
  });

  it("never carries a field outside the editable three", () => {
    const user = { ...saved, email: "a@b.c", role: "customer", is_active: true } as never;
    const result = changedFields(user, { ...saved, first_name: "Z" });
    expect(Object.keys(result)).toEqual(["first_name"]);
  });
});

describe("valuesFromUser", () => {
  it("picks just the editable fields", () => {
    expect(valuesFromUser({ ...saved, email: "a@b.c" } as never)).toEqual(saved);
  });
});

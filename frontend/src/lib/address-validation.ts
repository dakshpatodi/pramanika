/**
 * Client-side checks for the address form. They mirror the server's rules
 * (app/schemas/address.py) only to give instant feedback - the server
 * validates again and its message is shown if it disagrees.
 */

import type { Address, AddressInput, AddressUpdateInput } from "@/types/address";

/** Same loose international rule as registration: optional "+", then 7-15 digits, not starting with 0. */
export const PHONE_PATTERN = /^\+?[1-9]\d{6,14}$/;
/** Six-digit Indian PIN code, never starting with 0. */
export const PIN_PATTERN = /^[1-9][0-9]{5}$/;

/** How many addresses one account may save. The server enforces it (409); this only
 * lets the page say so before the user fills in a form. */
export const MAX_ADDRESSES = 20;

export type AddressField = "full_name" | "phone_number" | "address_line_1" | "address_line_2" | "city" | "state" | "postal_code";
export type AddressErrors = Partial<Record<AddressField, string>>;

const LIMITS: Record<AddressField, number> = {
  full_name: 150,
  phone_number: 16,
  address_line_1: 255,
  address_line_2: 255,
  city: 100,
  state: 100,
  postal_code: 6,
};

export function validateAddress(values: Pick<AddressInput, AddressField>): AddressErrors {
  const errors: AddressErrors = {};
  const v = {
    full_name: values.full_name.trim(),
    phone_number: values.phone_number.trim(),
    address_line_1: values.address_line_1.trim(),
    address_line_2: (values.address_line_2 ?? "").trim(),
    city: values.city.trim(),
    state: values.state.trim(),
    postal_code: values.postal_code.trim(),
  };

  if (!v.full_name) errors.full_name = "Enter the recipient's full name.";
  if (!v.phone_number) errors.phone_number = "Enter a phone number.";
  else if (!PHONE_PATTERN.test(v.phone_number)) errors.phone_number = "Use digits only, optionally starting with +.";
  if (!v.address_line_1) errors.address_line_1 = "Enter the street address.";
  if (!v.city) errors.city = "Enter the city.";
  if (!v.state) errors.state = "Enter the state.";
  if (!v.postal_code) errors.postal_code = "Enter the PIN code.";
  else if (!PIN_PATTERN.test(v.postal_code)) errors.postal_code = "Enter a valid 6-digit PIN code.";

  (Object.keys(LIMITS) as AddressField[]).forEach((field) => {
    if (!errors[field] && v[field].length > LIMITS[field]) errors[field] = `Must be at most ${LIMITS[field]} characters.`;
  });
  return errors;
}

/** Trimmed request body; an empty second line is sent as null. */
export function toAddressInput(values: Pick<AddressInput, AddressField>, isDefault: boolean): AddressInput {
  const line2 = (values.address_line_2 ?? "").trim();
  return {
    full_name: values.full_name.trim(),
    phone_number: values.phone_number.trim(),
    address_line_1: values.address_line_1.trim(),
    address_line_2: line2 === "" ? null : line2,
    city: values.city.trim(),
    state: values.state.trim(),
    postal_code: values.postal_code.trim(),
    is_default: isDefault,
  };
}

const EDITABLE: AddressField[] = ["full_name", "phone_number", "address_line_1", "address_line_2", "city", "state", "postal_code"];

/** What PATCH should carry: only fields whose trimmed value differs from the saved address.
 * Clearing the optional second line is sent as null. Empty result = nothing to save. */
export function diffAddress(saved: Address, edited: AddressInput): AddressUpdateInput {
  const next = toAddressInput(edited, false);
  const changes: AddressUpdateInput = {};
  for (const field of EDITABLE) {
    if (field === "address_line_2") {
      const before = saved.address_line_2 ?? null;
      const after = next.address_line_2 ?? null;
      if (before !== after) changes.address_line_2 = after;
    } else if (next[field] !== saved[field]) {
      changes[field] = next[field];
    }
  }
  return changes;
}

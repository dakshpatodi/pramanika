/**
 * Types mirroring the backend's Phase 6 address schemas
 * (app/schemas/address.py). Keep in sync manually.
 *
 * Delivery is India-only for now, so the
 * server always stores country "India" and the request has no country
 * field; the PIN code must be six digits and cannot start with 0.
 */

export interface Address {
  id: string;
  full_name: string;
  phone_number: string;
  address_line_1: string;
  address_line_2: string | null;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  is_default: boolean;
  created_at: string;
}

/** Body of POST /api/addresses. */
export interface AddressInput {
  full_name: string;
  /** Digits only with an optional leading "+", e.g. 9876543210 or +919876543210. */
  phone_number: string;
  address_line_1: string;
  address_line_2?: string | null;
  city: string;
  state: string;
  /** Six-digit Indian PIN code. */
  postal_code: string;
  /** Make this the default address (the first address is always the default). */
  is_default?: boolean;
}

/** Body of PATCH /api/addresses/{id}: only the fields that changed. `address_line_2`
 * may be null to clear it; every other field is required on a saved address.
 * There is no `is_default` here - the default moves through its own endpoint. */
export interface AddressUpdateInput {
  full_name?: string;
  phone_number?: string;
  address_line_1?: string;
  address_line_2?: string | null;
  city?: string;
  state?: string;
  postal_code?: string;
}

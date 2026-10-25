/**
 * Body of PATCH /api/users/me (app/schemas/user.py, UserUpdateRequest).
 *
 * Send only the fields that changed. Email, role and the account flags are
 * deliberately not here: the server refuses them (422), it does not ignore
 * them. The email is the login identity and cannot be changed from the
 * dashboard.
 */
export interface ProfileUpdateInput {
  first_name?: string;
  last_name?: string;
  /** Digits only with an optional leading "+", e.g. 9876543210 or +919876543210. */
  phone_number?: string;
}

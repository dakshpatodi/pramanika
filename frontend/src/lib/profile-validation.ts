/**
 * Client-side checks for the profile form. They mirror the server's rules
 * (app/schemas/user.py, UserUpdateRequest) only to give instant feedback;
 * the server validates again and its message is shown if it disagrees.
 */

import { PHONE_PATTERN } from "@/lib/address-validation";
import type { User } from "@/types/auth";
import type { ProfileUpdateInput } from "@/types/profile";

export const NAME_MAX_LENGTH = 100;

export type ProfileField = "first_name" | "last_name" | "phone_number";
export type ProfileValues = Record<ProfileField, string>;
export type ProfileErrors = Partial<Record<ProfileField, string>>;

const FIELDS: ProfileField[] = ["first_name", "last_name", "phone_number"];

export function validateProfile(values: ProfileValues): ProfileErrors {
  const errors: ProfileErrors = {};
  const first = values.first_name.trim();
  const last = values.last_name.trim();
  const phone = values.phone_number.trim();

  if (!first) errors.first_name = "Enter your first name.";
  else if (first.length > NAME_MAX_LENGTH) errors.first_name = `Must be at most ${NAME_MAX_LENGTH} characters.`;

  if (!last) errors.last_name = "Enter your last name.";
  else if (last.length > NAME_MAX_LENGTH) errors.last_name = `Must be at most ${NAME_MAX_LENGTH} characters.`;

  if (!phone) errors.phone_number = "Enter a phone number.";
  else if (!PHONE_PATTERN.test(phone)) errors.phone_number = "Use digits only, optionally starting with +.";

  return errors;
}

/** Only the fields whose trimmed value differs from the saved profile - what PATCH should carry. */
export function changedFields(user: Pick<User, ProfileField>, values: ProfileValues): ProfileUpdateInput {
  const changes: ProfileUpdateInput = {};
  for (const field of FIELDS) {
    const next = values[field].trim();
    if (next !== user[field]) changes[field] = next;
  }
  return changes;
}

export function valuesFromUser(user: Pick<User, ProfileField>): ProfileValues {
  return { first_name: user.first_name, last_name: user.last_name, phone_number: user.phone_number };
}

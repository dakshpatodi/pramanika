/**
 * Types mirroring the backend's Pydantic schemas (app/schemas/user.py,
 * app/schemas/auth.py, app/schemas/common.py). Keep these in sync
 * manually when those schemas change - there's no shared codegen
 * between the two stacks yet.
 */

export type UserRole = "customer" | "admin";

export interface User {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone_number: string;
  role: UserRole;
  is_active: boolean;
  is_verified: boolean;
  last_login: string | null;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface LoginResponseData extends TokenPair {
  user: User;
}

/** Matches app/schemas/common.py's APIResponse envelope. */
export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data?: T;
}
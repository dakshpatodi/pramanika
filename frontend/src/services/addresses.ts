/**
 * Address API calls (Phase 6 backend, /api/addresses).
 *
 * Uses the shared `apiClient` (access token attached, silent refresh on
 * 401), so the owner is always the logged-in user - there is no user id in
 * any request. List + add only; editing and deleting arrive in Phase 8.
 */

import { apiClient } from "@/lib/axios";
import type { Address, AddressInput } from "@/types/address";
import type { ApiResponse } from "@/types/auth";

/** The user's addresses, default first. */
export async function listAddresses(): Promise<Address[]> {
  const { data } = await apiClient.get<ApiResponse<Address[]>>("/api/addresses");
  return data.data as Address[];
}

export async function createAddress(input: AddressInput): Promise<Address> {
  const { data } = await apiClient.post<ApiResponse<Address>>("/api/addresses", input);
  return data.data as Address;
}
/**
 * Address API calls (Phase 6 backend, /api/addresses).
 *
 * Uses the shared `apiClient` (access token attached, silent refresh on
 * 401), so the owner is always the logged-in user - there is no user id in
 * any request.
 */

import { apiClient } from "@/lib/axios";
import type { Address, AddressInput, AddressUpdateInput } from "@/types/address";
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

/** Saves only the fields given. Orders already placed keep their own copy of the address. */
export async function updateAddress(addressId: string, input: AddressUpdateInput): Promise<Address> {
  const { data } = await apiClient.patch<ApiResponse<Address>>(`/api/addresses/${addressId}`, input);
  return data.data as Address;
}

/** Makes this the default address; resolves with the whole list, default first. */
export async function setDefaultAddress(addressId: string): Promise<Address[]> {
  const { data } = await apiClient.post<ApiResponse<Address[]>>(`/api/addresses/${addressId}/default`);
  return data.data as Address[];
}

/** Deletes an address; resolves with the addresses that remain, default first.
 * If it was the default, the server promotes another. Orders placed with it are untouched. */
export async function deleteAddress(addressId: string): Promise<Address[]> {
  const { data } = await apiClient.delete<ApiResponse<Address[]>>(`/api/addresses/${addressId}`);
  return data.data as Address[];
}

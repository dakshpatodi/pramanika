/**
 * Invoice API calls (Phase 8 backend, /api/invoices). Both go through the
 * shared `apiClient`: the access token is sent in the Authorization header
 * (never in a URL) and an expired one is refreshed silently.
 */

import axios from "axios";

import { apiClient } from "@/lib/axios";
import type { ApiResponse } from "@/types/auth";
import type { InvoiceList } from "@/types/invoice";

/** One page of the user's paid orders (one invoice each), newest first. */
export async function listInvoices(page: number = 1, pageSize: number = 10): Promise<InvoiceList> {
  const { data } = await apiClient.get<ApiResponse<InvoiceList>>("/api/invoices", {
    params: { page, page_size: pageSize },
  });
  return data.data as InvoiceList;
}

/**
 * The invoice PDF for one paid order, as a Blob.
 *
 * A failed request asked for a blob also carries its JSON error body as a
 * blob, so the server's message ("An invoice is available once the order has
 * been paid.") would be lost. It is read here and re-thrown as a plain Error,
 * which `getApiErrorMessage` shows as it is.
 */
export async function downloadInvoice(orderId: string): Promise<Blob> {
  try {
    const { data } = await apiClient.get<Blob>(`/api/invoices/${orderId}`, { responseType: "blob" });
    return data;
  } catch (error) {
    if (axios.isAxiosError(error) && typeof Blob !== "undefined" && error.response?.data instanceof Blob) {
      try {
        const body = JSON.parse(await error.response.data.text()) as { message?: unknown };
        if (typeof body.message === "string" && body.message.trim()) throw new Error(body.message);
      } catch (parsed) {
        if (parsed instanceof Error && !(parsed instanceof SyntaxError)) throw parsed;
        // Not JSON: fall through to the original error.
      }
    }
    throw error;
  }
}

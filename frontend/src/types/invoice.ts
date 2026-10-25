/** Mirrors app/schemas/invoice.py (Phase 8). Keep in sync manually. */

import type { PaginationMeta } from "@/types/order";

/** One paid order that has an invoice. */
export interface InvoiceSummary {
  order_id: string;
  order_number: string | null;
  order_date: string;
  total: number;
  /** Total units across all lines. */
  item_count: number;
  line_count: number;
}

export interface InvoiceList {
  invoices: InvoiceSummary[];
  pagination: PaginationMeta;
}

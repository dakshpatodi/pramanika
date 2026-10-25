import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { InvoiceList } from "@/types/invoice";

const { api } = vi.hoisted(() => ({ api: { listInvoices: vi.fn() } }));
vi.mock("@/services/invoices", () => api);

import { useInvoices } from "@/hooks/useInvoices";

const page = (n: number, totalPages = 3): InvoiceList => ({
  invoices: [{ order_id: `o${n}`, order_number: `PRM-${n}`, order_date: "2026-10-05T00:00:00Z", total: 10, item_count: 1, line_count: 1 }],
  pagination: { total: totalPages * 10, page: n, page_size: 10, total_pages: totalPages, has_next: n < totalPages, has_previous: n > 1 },
});
function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((res) => { resolve = res; });
  return { promise, resolve };
}
beforeEach(() => {
  api.listInvoices.mockReset();
});

describe("useInvoices", () => {
  it("loads the requested page", async () => {
    api.listInvoices.mockResolvedValue(page(1));
    const { result } = renderHook(() => useInvoices(1, 10));
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.data?.invoices[0].order_id).toBe("o1"));
    expect(api.listInvoices).toHaveBeenCalledWith(1, 10);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("keeps the previous page on screen while the next one loads", async () => {
    api.listInvoices.mockResolvedValueOnce(page(1));
    const { result, rerender } = renderHook(({ p }) => useInvoices(p, 10), { initialProps: { p: 1 } });
    await waitFor(() => expect(result.current.data?.pagination.page).toBe(1));
    const next = deferred<InvoiceList>();
    api.listInvoices.mockReturnValueOnce(next.promise);
    rerender({ p: 2 });
    expect(result.current.data?.pagination.page).toBe(1);
    expect(result.current.isLoading).toBe(true);
    await act(async () => { next.resolve(page(2)); });
    expect(result.current.data?.pagination.page).toBe(2);
  });

  it("ignores a response for a page the user already moved away from", async () => {
    const slow = deferred<InvoiceList>();
    api.listInvoices.mockReturnValueOnce(slow.promise);
    const { result, rerender } = renderHook(({ p }) => useInvoices(p, 10), { initialProps: { p: 1 } });
    api.listInvoices.mockResolvedValueOnce(page(2));
    rerender({ p: 2 });
    await waitFor(() => expect(result.current.data?.pagination.page).toBe(2));
    await act(async () => { slow.resolve(page(1)); });
    expect(result.current.data?.pagination.page).toBe(2);
    expect(result.current.isLoading).toBe(false);
  });

  it("reports the server's message and can reload", async () => {
    api.listInvoices.mockRejectedValueOnce(Object.assign(new Error("x"), { isAxiosError: true, response: { data: { success: false, message: "Down." } } }));
    const { result } = renderHook(() => useInvoices(1, 10));
    await waitFor(() => expect(result.current.error).toBe("Down."));
    expect(result.current.data).toBeNull();
    api.listInvoices.mockResolvedValueOnce(page(1));
    await act(async () => { await result.current.reload(); });
    expect(result.current.error).toBeNull();
    expect(result.current.data?.pagination.page).toBe(1);
  });

  it("falls back to a plain message", async () => {
    api.listInvoices.mockRejectedValue({});
    const { result } = renderHook(() => useInvoices(1, 10));
    await waitFor(() => expect(result.current.error).toBe("We couldn't load your invoices. Please try again."));
  });
});

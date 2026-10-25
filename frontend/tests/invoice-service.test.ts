import { beforeEach, describe, expect, it, vi } from "vitest";

const { client } = vi.hoisted(() => ({ client: { get: vi.fn() } }));
vi.mock("@/lib/axios", () => ({ apiClient: client }));

import { getApiErrorMessage } from "@/lib/errors";
import { downloadInvoice, listInvoices } from "@/services/invoices";

beforeEach(() => {
  client.get.mockReset(); // block body: a returned function would be run by Vitest as a teardown
});

const blobError = (body: string, status = 409) =>
  Object.assign(new Error("Request failed"), { isAxiosError: true, response: { status, data: new Blob([body], { type: "application/json" }) } });

describe("downloadInvoice", () => {
  it("asks for the PDF as a blob from the order's own path", async () => {
    const pdf = new Blob(["%PDF-1.3"], { type: "application/pdf" });
    client.get.mockResolvedValue({ data: pdf });
    expect(await downloadInvoice("o1")).toBe(pdf);
    expect(client.get).toHaveBeenCalledWith("/api/invoices/o1", { responseType: "blob" });
  });

  it("does not put any token or secret in the URL", async () => {
    client.get.mockResolvedValue({ data: new Blob(["x"]) });
    await downloadInvoice("o1");
    expect(client.get.mock.calls[0][0]).toBe("/api/invoices/o1");
    expect(client.get.mock.calls[0][0]).not.toMatch(/token|bearer|\?/i);
  });

  it("turns a blob-wrapped JSON error into the server's own message", async () => {
    client.get.mockRejectedValue(blobError(JSON.stringify({ success: false, message: "An invoice is available once the order has been paid." })));
    const error = await downloadInvoice("o1").catch((e) => e);
    expect(error).toBeInstanceOf(Error);
    expect(error.message).toBe("An invoice is available once the order has been paid.");
    expect(getApiErrorMessage(error)).toBe("An invoice is available once the order has been paid.");
  });

  it("keeps the original error when the body is not JSON", async () => {
    const failure = blobError("<html>bad gateway</html>", 502);
    client.get.mockRejectedValue(failure);
    await expect(downloadInvoice("o1")).rejects.toBe(failure);
  });

  it("keeps the original error when the JSON has no usable message", async () => {
    const failure = blobError(JSON.stringify({ success: false }), 500);
    client.get.mockRejectedValue(failure);
    await expect(downloadInvoice("o1")).rejects.toBe(failure);
  });

  it("passes any other failure (network down) through untouched", async () => {
    const failure = new Error("Network Error");
    client.get.mockRejectedValue(failure);
    await expect(downloadInvoice("o1")).rejects.toBe(failure);
  });
});

describe("listInvoices", () => {
  it("uses the API's page names and unwraps the envelope", async () => {
    client.get.mockResolvedValue({ data: { success: true, message: "ok", data: { invoices: [{ order_id: "o1" }], pagination: { total: 1 } } } });
    expect((await listInvoices(2, 10)).invoices[0].order_id).toBe("o1");
    expect(client.get).toHaveBeenCalledWith("/api/invoices", { params: { page: 2, page_size: 10 } });
  });
});

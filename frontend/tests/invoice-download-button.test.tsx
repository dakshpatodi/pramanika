import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { api, files } = vi.hoisted(() => ({ api: { downloadInvoice: vi.fn() }, files: { saveBlob: vi.fn() } }));
vi.mock("@/services/invoices", () => api);
vi.mock("@/lib/download", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/download")>()), saveBlob: files.saveBlob }));

import { InvoiceDownloadButton } from "@/components/invoices/InvoiceDownloadButton";

function deferred<T>() {
  let resolve!: (v: T) => void; let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
beforeEach(() => { api.downloadInvoice.mockReset(); files.saveBlob.mockReset(); });
afterEach(cleanup);

describe("InvoiceDownloadButton", () => {
  it("names the order for screen readers", () => {
    render(<InvoiceDownloadButton orderId="o1" orderNumber="PRM-2026-000042" />);
    expect(screen.getByRole("button", { name: "Download invoice for order PRM-2026-000042" })).toBeInTheDocument();
  });

  it("fetches that order's invoice and saves it under the order-number file name", async () => {
    const user = userEvent.setup();
    const blob = new Blob(["%PDF"]);
    api.downloadInvoice.mockResolvedValue(blob);
    render(<InvoiceDownloadButton orderId="o1" orderNumber="PRM-2026-000042" />);
    await user.click(screen.getByRole("button"));
    await waitFor(() => expect(files.saveBlob).toHaveBeenCalledTimes(1));
    expect(api.downloadInvoice).toHaveBeenCalledWith("o1");
    expect(files.saveBlob).toHaveBeenCalledWith(blob, "invoice-PRM-2026-000042.pdf");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("works for an order without a number", async () => {
    const user = userEvent.setup();
    api.downloadInvoice.mockResolvedValue(new Blob(["x"]));
    render(<InvoiceDownloadButton orderId="0123456789abcdef" orderNumber={null} />);
    await user.click(screen.getByRole("button", { name: "Download invoice" }));
    await waitFor(() => expect(files.saveBlob).toHaveBeenCalled());
    expect(files.saveBlob.mock.calls[0][1]).toBe("invoice-0123456789ab.pdf");
  });

  it("is disabled while preparing and ignores a second click", async () => {
    const user = userEvent.setup();
    const pending = deferred<Blob>();
    api.downloadInvoice.mockReturnValue(pending.promise);
    render(<InvoiceDownloadButton orderId="o1" orderNumber="PRM-1" />);
    await user.click(screen.getByRole("button"));
    const busy = screen.getByRole("button", { name: "Preparing invoice for order PRM-1" });
    expect(busy).toBeDisabled();
    expect(busy).toHaveTextContent("Preparing...");
    await user.click(busy);
    expect(api.downloadInvoice).toHaveBeenCalledTimes(1);
    pending.resolve(new Blob(["x"]));
    await waitFor(() => expect(screen.getByRole("button")).toBeEnabled());
    expect(files.saveBlob).toHaveBeenCalledTimes(1);
  });

  it("two clicks inside the same render pass still make one request (before the button can disable itself)", async () => {
    const pending = deferred<Blob>();
    api.downloadInvoice.mockReturnValue(pending.promise);
    render(<InvoiceDownloadButton orderId="o1" orderNumber="PRM-1" />);
    const button = screen.getByRole("button");
    act(() => { button.click(); button.click(); });
    expect(api.downloadInvoice).toHaveBeenCalledTimes(1);
    pending.resolve(new Blob(["x"]));
    await waitFor(() => expect(files.saveBlob).toHaveBeenCalledTimes(1));
  });

  it("shows the server's message when it refuses, saves nothing, and can be retried", async () => {
    const user = userEvent.setup();
    api.downloadInvoice.mockRejectedValueOnce(new Error("An invoice is available once the order has been paid."));
    render(<InvoiceDownloadButton orderId="o1" orderNumber="PRM-1" />);
    await user.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toHaveTextContent("An invoice is available once the order has been paid.");
    expect(files.saveBlob).not.toHaveBeenCalled();

    api.downloadInvoice.mockResolvedValueOnce(new Blob(["%PDF"]));
    await user.click(screen.getByRole("button"));
    await waitFor(() => expect(files.saveBlob).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("uses a plain message when the failure carries none (network down)", async () => {
    const user = userEvent.setup();
    api.downloadInvoice.mockRejectedValue({});
    render(<InvoiceDownloadButton orderId="o1" orderNumber="PRM-1" />);
    await user.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't download this invoice. Please try again.");
  });
});

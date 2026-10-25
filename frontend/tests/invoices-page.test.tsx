import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { InvoiceList, InvoiceSummary } from "@/types/invoice";

const { auth, router, api, files } = vi.hoisted(() => ({
  auth: { user: null as null | { id: string }, isLoading: false, isAuthenticated: true },
  router: { push: vi.fn() },
  api: { listInvoices: vi.fn(), downloadInvoice: vi.fn() },
  files: { saveBlob: vi.fn() },
}));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/dashboard/invoices" }));
vi.mock("@/services/invoices", () => api);
vi.mock("@/lib/download", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/download")>()), saveBlob: files.saveBlob }));

import InvoicesPage from "@/app/dashboard/invoices/page";

const invoice = (n: number, over: Partial<InvoiceSummary> = {}): InvoiceSummary => ({
  order_id: `order-${n}`, order_number: `PRM-2026-00000${n}`, order_date: "2026-10-05T10:30:00Z", total: 100 * n, item_count: n, line_count: 1, ...over,
});
const list = (invoices: InvoiceSummary[], page = 1, totalPages = 1, total = invoices.length): InvoiceList => ({
  invoices, pagination: { total, page, page_size: 10, total_pages: totalPages, has_next: page < totalPages, has_previous: page > 1 },
});

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  files.saveBlob.mockReset();
  router.push.mockReset();
  auth.user = { id: "u1" };
  auth.isLoading = false;
  auth.isAuthenticated = true;
});
afterEach(cleanup);

describe("Invoices page", () => {
  it("lists paid orders with number, date, items and total, inside the account frame", async () => {
    api.listInvoices.mockResolvedValue(list([invoice(2), invoice(1)]));
    render(<InvoicesPage />);
    expect(await screen.findByText("PRM-2026-000002")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Invoices");
    expect(within(screen.getByRole("navigation", { name: "Account" })).getByRole("link", { name: "Invoices" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText(/2 items/)).toBeInTheDocument();
    expect(screen.getByText(/1 item\b/)).toBeInTheDocument();
    expect(screen.getByText(/₹200\.00/)).toBeInTheDocument();
    expect(api.listInvoices).toHaveBeenCalledWith(1, 10);
  });

  it("downloads the invoice of the row that was clicked", async () => {
    const user = userEvent.setup();
    api.listInvoices.mockResolvedValue(list([invoice(2), invoice(1)]));
    const blob = new Blob(["%PDF"]);
    api.downloadInvoice.mockResolvedValue(blob);
    render(<InvoicesPage />);
    await user.click(await screen.findByRole("button", { name: "Download invoice for order PRM-2026-000001" }));
    await waitFor(() => expect(files.saveBlob).toHaveBeenCalledTimes(1));
    expect(api.downloadInvoice).toHaveBeenCalledWith("order-1");
    expect(files.saveBlob).toHaveBeenCalledWith(blob, "invoice-PRM-2026-000001.pdf");
  });

  it("a failed download is reported on its own row and the others still work", async () => {
    const user = userEvent.setup();
    api.listInvoices.mockResolvedValue(list([invoice(2), invoice(1)]));
    api.downloadInvoice.mockRejectedValueOnce(new Error("Order was not found."));
    render(<InvoicesPage />);
    await user.click(await screen.findByRole("button", { name: "Download invoice for order PRM-2026-000002" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Order was not found.");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    api.downloadInvoice.mockResolvedValueOnce(new Blob(["x"]));
    await user.click(screen.getByRole("button", { name: "Download invoice for order PRM-2026-000001" }));
    await waitFor(() => expect(files.saveBlob).toHaveBeenCalledTimes(1));
  });

  it("explains when there are none", async () => {
    api.listInvoices.mockResolvedValue(list([]));
    render(<InvoicesPage />);
    expect(await screen.findByText("No invoices yet")).toBeInTheDocument();
    expect(screen.getByText(/once it has been paid/)).toBeInTheDocument();
  });

  it("shows a loading placeholder, then an error with a working retry", async () => {
    const user = userEvent.setup();
    api.listInvoices.mockReturnValueOnce(new Promise(() => {}));
    render(<InvoicesPage />);
    expect(screen.getByRole("status", { name: "Loading your invoices" })).toBeInTheDocument();
    cleanup();

    api.listInvoices.mockReset();
    api.listInvoices.mockRejectedValueOnce(Object.assign(new Error("x"), { isAxiosError: true, response: { data: { success: false, message: "Invoices are unavailable." } } }));
    render(<InvoicesPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Invoices are unavailable.");
    api.listInvoices.mockResolvedValue(list([invoice(1)]));
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("PRM-2026-000001")).toBeInTheDocument();
  });

  it("pages through the list", async () => {
    const user = userEvent.setup();
    api.listInvoices.mockImplementation(async (page: number) => (page === 1 ? list([invoice(1)], 1, 2, 11) : list([invoice(2)], 2, 2, 11)));
    render(<InvoicesPage />);
    await screen.findByText("PRM-2026-000001");
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("PRM-2026-000002")).toBeInTheDocument();
    expect(api.listInvoices).toHaveBeenLastCalledWith(2, 10);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("renders nothing for a visitor and never calls the API", () => {
    auth.user = null;
    auth.isAuthenticated = false;
    const { container } = render(<InvoicesPage />);
    expect(container).toBeEmptyDOMElement();
    expect(router.push).toHaveBeenCalledWith("/login?redirect=%2Fdashboard%2Finvoices");
    expect(api.listInvoices).not.toHaveBeenCalled();
  });
});

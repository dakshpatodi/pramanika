"use client";

import { useState } from "react";
import { FileText } from "lucide-react";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { InvoiceDownloadButton } from "@/components/invoices/InvoiceDownloadButton";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useInvoices } from "@/hooks/useInvoices";
import { formatMoney } from "@/lib/money";
import { formatOrderDate } from "@/lib/order-format";

const PAGE_SIZE = 10;

function InvoicesContent() {
  const [page, setPage] = useState(1);
  const { data, isLoading, error, reload } = useInvoices(page, PAGE_SIZE);

  let body: React.ReactNode;
  if (!data && error) {
    body = (
      <Card className="flex flex-col items-center gap-4 px-6 py-14 text-center">
        <p role="alert" className="max-w-sm text-foreground">
          {error}
        </p>
        <Button variant="primary" onClick={() => void reload()} disabled={isLoading}>
          {isLoading ? "Retrying..." : "Try again"}
        </Button>
      </Card>
    );
  } else if (!data) {
    body = (
      <div role="status" aria-label="Loading your invoices" className="flex flex-col gap-4">
        {[0, 1, 2].map((n) => (
          <div key={n} className="h-24 animate-pulse rounded-2xl bg-muted" />
        ))}
      </div>
    );
  } else if (data.pagination.total === 0) {
    body = (
      <Card className="flex flex-col items-center gap-3 px-6 py-16 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-blob bg-primary-light text-primary">
          <FileText className="h-7 w-7" aria-hidden="true" />
        </span>
        <h2 className="font-display text-xl font-semibold text-foreground">No invoices yet</h2>
        <p className="max-w-sm text-sm text-muted-foreground">An invoice is available for an order once it has been paid.</p>
      </Card>
    );
  } else {
    const { invoices, pagination } = data;
    body = (
      <div className="flex flex-col gap-4">
        {error ? (
          <p role="alert" className="text-sm text-accent-dark">
            {error}
          </p>
        ) : null}
        <ul aria-busy={isLoading} className="flex flex-col gap-4">
          {invoices.map((invoice) => (
            <li key={invoice.order_id}>
              <Card className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-col gap-1">
                  <span className="font-display text-base font-semibold text-foreground">{invoice.order_number ?? "Order"}</span>
                  <span className="text-sm text-muted-foreground">Placed on {formatOrderDate(invoice.order_date)}</span>
                  <span className="text-sm text-foreground">
                    {invoice.item_count} {invoice.item_count === 1 ? "item" : "items"} &middot; {formatMoney(invoice.total)}
                  </span>
                </div>
                <InvoiceDownloadButton orderId={invoice.order_id} orderNumber={invoice.order_number} />
              </Card>
            </li>
          ))}
        </ul>

        {pagination.total_pages > 1 ? (
          <nav aria-label="Invoice pages" className="flex items-center justify-between gap-3">
            <Button variant="outline" size="sm" disabled={!pagination.has_previous || isLoading} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {pagination.page} of {pagination.total_pages}
            </span>
            <Button variant="outline" size="sm" disabled={!pagination.has_next || isLoading} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </nav>
        ) : null}
      </div>
    );
  }

  return (
    <DashboardShell title="Invoices" description="Download an invoice for any order you have paid.">
      {body}
    </DashboardShell>
  );
}

export default function InvoicesPage() {
  return (
    <ProtectedRoute>
      <InvoicesContent />
    </ProtectedRoute>
  );
}

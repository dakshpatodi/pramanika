"use client";

import { useRef, useState } from "react";
import { Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import { invoiceFileName, saveBlob } from "@/lib/download";
import { getApiErrorMessage } from "@/lib/errors";
import { downloadInvoice } from "@/services/invoices";

interface InvoiceDownloadButtonProps {
  orderId: string;
  orderNumber: string | null;
  variant?: "primary" | "outline";
}

/**
 * Downloads one order's invoice PDF. Used on the invoices page and on a paid
 * order's detail page. A second click while it is working does nothing; a
 * failure is shown with the server's own message and can simply be retried.
 */
export function InvoiceDownloadButton({ orderId, orderNumber, variant = "outline" }: InvoiceDownloadButtonProps) {
  const [isWorking, setIsWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const workingRef = useRef(false);

  async function download() {
    if (workingRef.current) return;
    workingRef.current = true;
    setIsWorking(true);
    setError(null);
    try {
      const blob = await downloadInvoice(orderId);
      saveBlob(blob, invoiceFileName(orderNumber, orderId));
    } catch (err) {
      setError(getApiErrorMessage(err, "We couldn't download this invoice. Please try again."));
    } finally {
      workingRef.current = false;
      setIsWorking(false);
    }
  }

  const label = orderNumber ? ` for order ${orderNumber}` : "";
  return (
    <div className="flex flex-col items-start gap-1.5">
      <Button
        type="button"
        variant={variant}
        size="sm"
        disabled={isWorking}
        onClick={() => void download()}
        aria-label={isWorking ? `Preparing invoice${label}` : `Download invoice${label}`}
      >
        <Download aria-hidden="true" />
        {isWorking ? "Preparing..." : "Download invoice"}
      </Button>
      {error ? (
        <p role="alert" className="max-w-xs text-xs text-accent-dark">
          {error}
        </p>
      ) : null}
    </div>
  );
}

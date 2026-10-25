/** Names and saves a file the app fetched itself (e.g. an invoice PDF). */

/** `invoice-PRM-2026-000042.pdf`; anything odd in the number becomes `_`. */
export function invoiceFileName(orderNumber: string | null, orderId: string): string {
  const base = (orderNumber ?? orderId.slice(0, 12)).replace(/[^A-Za-z0-9._-]/g, "_");
  return `invoice-${base}.pdf`;
}

/** Hands a Blob to the browser as a download. The temporary link is removed again straight away. */
export function saveBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    // After the click has been handled; revoking synchronously can cancel the download in some browsers.
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
}

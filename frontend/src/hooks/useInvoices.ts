"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getApiErrorMessage } from "@/lib/errors";
import * as invoicesApi from "@/services/invoices";
import type { InvoiceList } from "@/types/invoice";

export interface UseInvoices {
  /** The requested page; null until it first loads. The previous page stays
   * in place while the next one loads, so the list never flashes empty. */
  data: InvoiceList | null;
  isLoading: boolean;
  error: string | null;
  reload: () => Promise<void>;
}

/** One page of the user's invoices, newest first. A response for a page the
 * user has already moved away from is ignored. */
export function useInvoices(page: number, pageSize: number = 10): UseInvoices {
  const [data, setData] = useState<InvoiceList | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const requestRef = useRef(0);
  const wantedRef = useRef({ page, pageSize });

  const load = useCallback(async () => {
    const request = ++requestRef.current;
    const wanted = wantedRef.current;
    setIsLoading(true);
    setError(null);
    try {
      const list = await invoicesApi.listInvoices(wanted.page, wanted.pageSize);
      if (requestRef.current === request) setData(list);
    } catch (err) {
      if (requestRef.current === request) {
        setError(getApiErrorMessage(err, "We couldn't load your invoices. Please try again."));
      }
    } finally {
      if (requestRef.current === request) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    wantedRef.current = { page, pageSize };
    void load();
  }, [page, pageSize, load]);

  return { data, isLoading, error, reload: load };
}

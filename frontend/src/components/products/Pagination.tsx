"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { PaginationMeta } from "@/types/product";

interface PaginationProps {
  pagination: PaginationMeta;
  onPageChange: (page: number) => void;
}

export function Pagination({ pagination, onPageChange }: PaginationProps) {
  const { page, total_pages, has_next, has_previous } = pagination;

  if (total_pages <= 1) return null;

  // Show at most 5 page numbers, centered around the current page,
  // rather than every page for a large catalogue.
  const start = Math.max(1, page - 2);
  const end = Math.min(total_pages, start + 4);
  const pages: number[] = [];
  for (let p = start; p <= end; p++) pages.push(p);

  return (
    <nav className="flex items-center justify-center gap-1.5" aria-label="Pagination">
      <Button
        variant="outline"
        size="icon"
        disabled={!has_previous}
        onClick={() => onPageChange(page - 1)}
        aria-label="Previous page"
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>

      {pages.map((p) => (
        <Button
          key={p}
          variant={p === page ? "primary" : "outline"}
          size="icon"
          onClick={() => onPageChange(p)}
          aria-current={p === page ? "page" : undefined}
        >
          {p}
        </Button>
      ))}

      <Button
        variant="outline"
        size="icon"
        disabled={!has_next}
        onClick={() => onPageChange(page + 1)}
        aria-label="Next page"
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
    </nav>
  );
}
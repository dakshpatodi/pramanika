"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface PriceRangeFilterProps {
  minPrice: string;
  maxPrice: string;
  onApply: (minPrice: string, maxPrice: string) => void;
}

/**
 * Local state + an explicit Apply button, rather than firing a request
 * on every keystroke - typing "500" one digit at a time shouldn't cause
 * three separate API calls.
 *
 * The useEffect below re-syncs local state whenever the external value
 * changes (e.g. the page's "Clear filters" button resets minPrice/maxPrice
 * to "") - without it, these inputs would visually keep showing stale
 * values after a clear, since useState's initial value only applies on
 * first mount.
 */
export function PriceRangeFilter({ minPrice, maxPrice, onApply }: PriceRangeFilterProps) {
  const [localMin, setLocalMin] = useState(minPrice);
  const [localMax, setLocalMax] = useState(maxPrice);

  useEffect(() => {
    setLocalMin(minPrice);
    setLocalMax(maxPrice);
  }, [minPrice, maxPrice]);

  return (
    <div className="flex items-center gap-2">
      <Input
        type="number"
        min={0}
        placeholder="Min"
        value={localMin}
        onChange={(event) => setLocalMin(event.target.value)}
        className="w-24"
      />
      <span className="text-sm text-muted-foreground">to</span>
      <Input
        type="number"
        min={0}
        placeholder="Max"
        value={localMax}
        onChange={(event) => setLocalMax(event.target.value)}
        className="w-24"
      />
      <Button type="button" variant="outline" size="sm" onClick={() => onApply(localMin, localMax)}>
        Apply
      </Button>
    </div>
  );
}
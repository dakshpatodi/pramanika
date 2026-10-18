"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Milliseconds left until `deadline` (an ISO time), or null if there is none.
 * Ticks once a second while under an hour is left (every 30 s beyond that) and
 * calls `onElapsed` ONCE when the deadline passes.
 *
 * Display only. The browser's clock can be wrong, so reaching zero does not
 * decide anything: `onElapsed` is where the page asks the SERVER again.
 */
export function useTimeLeft(deadline: string | null, onElapsed?: () => void): number | null {
  const target = deadline ? new Date(deadline).getTime() : NaN;
  const [now, setNow] = useState(() => Date.now());
  const elapsedFor = useRef<string | null>(null);
  const callback = useRef(onElapsed);
  callback.current = onElapsed;

  useEffect(() => {
    if (Number.isNaN(target)) return undefined;
    setNow(Date.now());
    const left = target - Date.now();
    if (left <= 0) return undefined;
    const interval = setInterval(() => setNow(Date.now()), left > 3_600_000 ? 30_000 : 1_000);
    return () => clearInterval(interval);
  }, [target]);

  const left = Number.isNaN(target) ? null : Math.max(0, target - now);

  useEffect(() => {
    if (left === 0 && deadline && elapsedFor.current !== deadline) {
      elapsedFor.current = deadline;
      callback.current?.();
    }
  }, [left, deadline]);

  return left;
}

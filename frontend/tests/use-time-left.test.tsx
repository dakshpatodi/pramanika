import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useTimeLeft } from "@/hooks/useTimeLeft";

const START = new Date("2026-10-12T10:00:00Z").getTime();
const at = (ms: number) => new Date(START + ms).toISOString();

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(START);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("useTimeLeft", () => {
  it("is null without a deadline and never calls back", () => {
    const onElapsed = vi.fn();
    const { result } = renderHook(() => useTimeLeft(null, onElapsed));
    act(() => { vi.advanceTimersByTime(10 * 60_000); });
    expect(result.current).toBeNull();
    expect(onElapsed).not.toHaveBeenCalled();
  });

  it("counts down once a second when under an hour is left", () => {
    const { result } = renderHook(() => useTimeLeft(at(30_000)));
    expect(result.current).toBe(30_000);
    act(() => { vi.advanceTimersByTime(1_000); });
    expect(result.current).toBe(29_000);
    act(() => { vi.advanceTimersByTime(4_000); });
    expect(result.current).toBe(25_000);
  });

  it("ticks only every 30 seconds when more than an hour is left", () => {
    const { result } = renderHook(() => useTimeLeft(at(2 * 3_600_000)));
    act(() => { vi.advanceTimersByTime(10_000); });
    expect(result.current).toBe(2 * 3_600_000);
    act(() => { vi.advanceTimersByTime(20_000); });
    expect(result.current).toBe(2 * 3_600_000 - 30_000);
  });

  it("calls onElapsed exactly once when the deadline passes, and stays at zero", () => {
    const onElapsed = vi.fn();
    const { result } = renderHook(() => useTimeLeft(at(3_000), onElapsed));
    act(() => { vi.advanceTimersByTime(2_000); });
    expect(onElapsed).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(1_500); });
    expect(result.current).toBe(0);
    expect(onElapsed).toHaveBeenCalledTimes(1);
    act(() => { vi.advanceTimersByTime(60_000); });
    expect(result.current).toBe(0);
    expect(onElapsed).toHaveBeenCalledTimes(1);
  });

  it("a deadline already in the past reports zero and calls back once", () => {
    const onElapsed = vi.fn();
    const { result } = renderHook(() => useTimeLeft(at(-60_000), onElapsed));
    expect(result.current).toBe(0);
    expect(onElapsed).toHaveBeenCalledTimes(1);
  });

  it("a new deadline restarts the countdown and can call back again", () => {
    const onElapsed = vi.fn();
    const { result, rerender } = renderHook(({ d }) => useTimeLeft(d, onElapsed), { initialProps: { d: at(1_000) } });
    act(() => { vi.advanceTimersByTime(1_500); });
    expect(onElapsed).toHaveBeenCalledTimes(1);
    rerender({ d: at(20_000) });
    expect(result.current).toBe(18_500);
    act(() => { vi.advanceTimersByTime(19_000); });
    expect(onElapsed).toHaveBeenCalledTimes(2);
  });

  it("an unreadable deadline is treated as none", () => {
    const { result } = renderHook(() => useTimeLeft("not a date"));
    expect(result.current).toBeNull();
  });

  it("stops its timer on unmount", () => {
    const { unmount } = renderHook(() => useTimeLeft(at(60_000)));
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("uses the latest callback without restarting", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ cb }) => useTimeLeft(at(2_000), cb), { initialProps: { cb: first } });
    rerender({ cb: second });
    act(() => { vi.advanceTimersByTime(2_500); });
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });
});

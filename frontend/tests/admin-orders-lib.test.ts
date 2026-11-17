import { describe, expect, it } from "vitest";

import {
  FULFILMENT_STEPS,
  NEXT_ACTION_LABEL,
  addressLines,
  confirmBody,
  dayRangeBackwards,
  dayRangeParams,
  isOrderStatusFilter,
  stepIndex,
  whyNoNextStep,
} from "@/lib/admin-orders";

describe("fulfilment steps", () => {
  it("run confirmed, processing, shipped, delivered", () => {
    expect(FULFILMENT_STEPS.map((s) => s.status)).toEqual(["confirmed", "processing", "shipped", "delivered"]);
  });
  it("stepIndex places a paid order on the path and others off it", () => {
    expect(stepIndex("confirmed")).toBe(0);
    expect(stepIndex("delivered")).toBe(3);
    for (const off of ["pending", "cancelled", "refunded"] as const) expect(stepIndex(off)).toBe(-1);
  });
  it("labels each action and warns that it cannot be undone", () => {
    expect(NEXT_ACTION_LABEL).toEqual({ processing: "Mark as processing", shipped: "Mark as shipped", delivered: "Mark as delivered" });
    for (const target of ["processing", "shipped", "delivered"] as const) expect(confirmBody(target)).toMatch(/cannot be undone/);
    expect(confirmBody("shipped")).toMatch(/left you/);
  });
});

describe("whyNoNextStep", () => {
  it("explains each way an order can be stuck", () => {
    expect(whyNoNextStep({ status: "delivered", payment_status: "paid", cancellation_reason: null })).toMatch(/delivered/);
    expect(whyNoNextStep({ status: "cancelled", payment_status: "pending", cancellation_reason: "expired" })).toMatch(/not paid in time/);
    expect(whyNoNextStep({ status: "cancelled", payment_status: "pending", cancellation_reason: "customer" })).toMatch(/was cancelled/);
    expect(whyNoNextStep({ status: "refunded", payment_status: "refunded", cancellation_reason: null })).toMatch(/refunded/);
    expect(whyNoNextStep({ status: "pending", payment_status: "pending", cancellation_reason: null })).toMatch(/not been paid/);
    expect(whyNoNextStep({ status: "confirmed", payment_status: "paid", cancellation_reason: null })).toMatch(/cannot be moved forward/);
  });
});

describe("addressLines", () => {
  it("prints the address in order, joining city, state and PIN", () => {
    expect(
      addressLines({ full_name: "Asha", phone_number: "98", address_line_1: "12 MG Road", address_line_2: "Flat 3", city: "Pune", state: "MH", postal_code: "411001", country: "India" })
    ).toEqual(["Asha", "12 MG Road", "Flat 3", "Pune, MH, 411001", "India", "98"]);
  });
  it("skips empty and blank parts", () => {
    expect(
      addressLines({ full_name: null, phone_number: " ", address_line_1: "x", address_line_2: null, city: null, state: "MH", postal_code: null, country: null })
    ).toEqual(["x", "MH"]);
    expect(addressLines({ full_name: null, phone_number: null, address_line_1: null, address_line_2: null, city: null, state: null, postal_code: null, country: null })).toEqual([]);
  });
});

describe("day range", () => {
  it("covers whole days in India time", () => {
    expect(dayRangeParams("2026-10-01", "2026-10-31")).toEqual({
      created_from: "2026-10-01T00:00:00+05:30",
      created_to: "2026-10-31T23:59:59.999+05:30",
    });
  });
  it("leaves out a blank or malformed day", () => {
    expect(dayRangeParams("", "")).toEqual({});
    expect(dayRangeParams("2026-10-01", "")).toEqual({ created_from: "2026-10-01T00:00:00+05:30" });
    expect(dayRangeParams("01/10/2026", "2026-1-5")).toEqual({});
  });
  it("detects an end before the start, but not a single day or a missing end", () => {
    expect(dayRangeBackwards("2026-10-10", "2026-10-09")).toBe(true);
    expect(dayRangeBackwards("2026-10-10", "2026-10-10")).toBe(false);
    expect(dayRangeBackwards("2026-10-10", "")).toBe(false);
    expect(dayRangeBackwards("", "2026-10-09")).toBe(false);
  });
});

describe("isOrderStatusFilter", () => {
  it("allows the seven statuses only", () => {
    for (const ok of ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled", "refunded"]) expect(isOrderStatusFilter(ok)).toBe(true);
    for (const bad of ["", "paid", "PENDING", undefined, ["pending"], 1, "pending; drop"]) expect(isOrderStatusFilter(bad)).toBe(false);
  });
});

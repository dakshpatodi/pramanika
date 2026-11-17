import { describe, expect, it } from "vitest";

import {
  MAX_STOCK,
  describeStockEvent,
  isStockFilter,
  resultingQuantity,
  stockUpdateInput,
  thresholdUpdateInput,
  validateStock,
  validateThreshold,
  type StockFormValues,
} from "@/lib/admin-inventory-form";

const form = (o: Partial<StockFormValues> = {}): StockFormValues => ({ mode: "add", amount: "5", reason: "", ...o });

describe("validateStock", () => {
  it("accepts a normal add, remove and set", () => {
    expect(validateStock(form())).toEqual({});
    expect(validateStock(form({ mode: "remove", amount: "3" }))).toEqual({});
    expect(validateStock(form({ mode: "set", amount: "0" }))).toEqual({});
  });
  it("needs a number, in words that fit the mode", () => {
    expect(validateStock(form({ amount: "  " })).amount).toBe("Enter how many units.");
    expect(validateStock(form({ mode: "set", amount: "" })).amount).toBe("Enter the new count.");
  });
  it.each(["-3", "+3", "2.5", "1e3", "abc", "1,000", "0x10"])("refuses %s", (amount) => {
    expect(validateStock(form({ amount })).amount).toBe("Enter a whole number, no decimals or signs.");
  });
  it("adding or removing 0 is refused, but a counted stock of 0 is fine", () => {
    expect(validateStock(form({ amount: "0" })).amount).toBe("Enter at least 1 unit.");
    expect(validateStock(form({ mode: "remove", amount: "0" })).amount).toBe("Enter at least 1 unit.");
    expect(validateStock(form({ mode: "set", amount: "0" })).amount).toBeUndefined();
  });
  it("stops at the maximum", () => {
    expect(validateStock(form({ amount: String(MAX_STOCK) })).amount).toBeUndefined();
    expect(validateStock(form({ amount: String(MAX_STOCK + 1) })).amount).toMatch(/at most 10,00,000/);
  });
  it("limits the note to 200 characters after trimming", () => {
    expect(validateStock(form({ reason: "x".repeat(200) })).reason).toBeUndefined();
    expect(validateStock(form({ reason: `  ${"x".repeat(200)}  ` })).reason).toBeUndefined();
    expect(validateStock(form({ reason: "x".repeat(201) })).reason).toBe("Use at most 200 characters.");
  });
});

describe("resultingQuantity", () => {
  it("shows what the change would leave", () => {
    expect(resultingQuantity(50, form({ amount: "5" }))).toBe(55);
    expect(resultingQuantity(50, form({ mode: "remove", amount: "5" }))).toBe(45);
    expect(resultingQuantity(50, form({ mode: "set", amount: "12" }))).toBe(12);
    expect(resultingQuantity(50, form({ mode: "remove", amount: "80" }))).toBe(-30);
  });
  it("is null until the amount is a whole number", () => {
    expect(resultingQuantity(50, form({ amount: "" }))).toBeNull();
    expect(resultingQuantity(50, form({ amount: "x" }))).toBeNull();
  });
});

describe("stockUpdateInput", () => {
  it("add is a positive adjust_by, remove a negative one", () => {
    expect(stockUpdateInput(form({ amount: " 5 " }), 50)).toEqual({ adjust_by: 5 });
    expect(stockUpdateInput(form({ mode: "remove", amount: "5" }), 50)).toEqual({ adjust_by: -5 });
  });
  it("set sends the count the admin SAW as expected_quantity, never adjust_by", () => {
    const body = stockUpdateInput(form({ mode: "set", amount: "12" }), 50);
    expect(body).toEqual({ quantity: 12, expected_quantity: 50 });
    expect(body).not.toHaveProperty("adjust_by");
  });
  it("sends a trimmed note only when there is one", () => {
    expect(stockUpdateInput(form({ reason: "  Supplier delivery " }), 1)).toEqual({ adjust_by: 5, reason: "Supplier delivery" });
    expect(stockUpdateInput(form({ reason: "   " }), 1)).toEqual({ adjust_by: 5 });
  });
  it("never sends reserved_quantity", () => {
    for (const mode of ["add", "remove", "set"] as const) {
      expect(JSON.stringify(stockUpdateInput(form({ mode }), 1))).not.toContain("reserved");
    }
  });
});

describe("threshold", () => {
  it("accepts 0 and whole numbers up to the maximum", () => {
    expect(validateThreshold("0")).toBeUndefined();
    expect(validateThreshold(" 25 ")).toBeUndefined();
    expect(validateThreshold(String(MAX_STOCK))).toBeUndefined();
  });
  it("refuses blanks, decimals, signs and too much", () => {
    expect(validateThreshold("")).toMatch(/Enter a number/);
    expect(validateThreshold("2.5")).toMatch(/whole number/);
    expect(validateThreshold("-1")).toMatch(/whole number/);
    expect(validateThreshold(String(MAX_STOCK + 1))).toMatch(/at most/);
  });
  it("is sent alone, as a number", () => {
    expect(thresholdUpdateInput(" 15 ")).toEqual({ low_stock_threshold: 15 });
  });
});

describe("isStockFilter", () => {
  it("allows only the three values the API takes", () => {
    for (const ok of ["ok", "low", "out"]) expect(isStockFilter(ok)).toBe(true);
    for (const bad of ["", "all", "LOW", undefined, null, ["low"], 3]) expect(isStockFilter(bad)).toBe(false);
  });
});

describe("describeStockEvent", () => {
  const event = (before: Record<string, unknown> | null, after: Record<string, unknown> | null, action = "inventory.update") => ({ action, before, after });
  it("words an addition, a removal and a stock take", () => {
    expect(describeStockEvent(event({ quantity: 50 }, { quantity: 60, method: "adjust", adjust_by: 10 })).summary).toBe("Stock 50 → 60 (added 10)");
    expect(describeStockEvent(event({ quantity: 50 }, { quantity: 45, method: "adjust", adjust_by: -5 })).summary).toBe("Stock 50 → 45 (removed 5)");
    expect(describeStockEvent(event({ quantity: 50 }, { quantity: 42, method: "set" })).summary).toBe("Stock 50 → 42 (set by stock take)");
  });
  it("words a threshold change, alone or with stock", () => {
    expect(describeStockEvent(event({ low_stock_threshold: 10 }, { low_stock_threshold: 20 })).summary).toBe("Low-stock warning at 10 → 20");
    expect(
      describeStockEvent(event({ quantity: 1, low_stock_threshold: 2 }, { quantity: 3, method: "set", low_stock_threshold: 4 })).summary
    ).toBe("Stock 1 → 3 (set by stock take); Low-stock warning at 2 → 4");
  });
  it("returns the note when there is one", () => {
    expect(describeStockEvent(event({ quantity: 1 }, { quantity: 2, reason: "Recount" })).reason).toBe("Recount");
    expect(describeStockEvent(event({ quantity: 1 }, { quantity: 2 })).reason).toBeNull();
    expect(describeStockEvent(event({ quantity: 1 }, { quantity: 2, reason: "" })).reason).toBeNull();
  });
  it("copes with missing or odd data", () => {
    expect(describeStockEvent(event(null, { quantity: 7 })).summary).toBe("Stock now 7");
    expect(describeStockEvent(event(null, null)).summary).toBe("inventory.update");
    expect(describeStockEvent(event({ quantity: "x" }, { quantity: "y" }, "inventory.other")).summary).toBe("inventory.other");
  });
});

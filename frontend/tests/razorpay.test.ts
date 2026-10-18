import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The module keeps "is the script loading" in a variable, so every test gets a fresh copy.
async function freshModule() {
  vi.resetModules();
  return await import("@/lib/razorpay");
}

const scripts = () => Array.from(document.head.querySelectorAll("script")) as HTMLScriptElement[];

beforeEach(() => {
  delete window.Razorpay;
  document.head.innerHTML = "";
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  delete window.Razorpay;
  document.head.innerHTML = "";
});

describe("loadRazorpayScript", () => {
  it("adds ONE script tag pointing at Razorpay's own https URL and resolves when it has loaded", async () => {
    const { loadRazorpayScript, RAZORPAY_SCRIPT_URL } = await freshModule();
    const first = loadRazorpayScript();
    const second = loadRazorpayScript(); // concurrent callers share the tag
    expect(scripts()).toHaveLength(1);
    expect(scripts()[0].src).toBe(RAZORPAY_SCRIPT_URL);
    expect(RAZORPAY_SCRIPT_URL).toBe("https://checkout.razorpay.com/v1/checkout.js");

    window.Razorpay = class {} as never;
    scripts()[0].onload?.(new Event("load"));
    await expect(first).resolves.toBeUndefined();
    await expect(second).resolves.toBeUndefined();
  });

  it("does not add a script when the SDK is already there", async () => {
    window.Razorpay = class {} as never;
    const { loadRazorpayScript } = await freshModule();
    await expect(loadRazorpayScript()).resolves.toBeUndefined();
    expect(scripts()).toHaveLength(0);
  });

  it("rejects with a customer-readable message when the script fails, removes the tag, and tries again next time", async () => {
    const { loadRazorpayScript } = await freshModule();
    const failing = loadRazorpay(loadRazorpayScript);
    scripts()[0].onerror?.(new Event("error"));
    await expect(failing).rejects.toThrow(/couldn't load the payment window/);
    expect(scripts()).toHaveLength(0);

    const retry = loadRazorpayScript(); // a failure is not remembered
    expect(scripts()).toHaveLength(1);
    window.Razorpay = class {} as never;
    scripts()[0].onload?.(new Event("load"));
    await expect(retry).resolves.toBeUndefined();
  });

  it("rejects if the script loads but defines no Razorpay", async () => {
    const { loadRazorpayScript } = await freshModule();
    const p = loadRazorpay(loadRazorpayScript);
    scripts()[0].onload?.(new Event("load"));
    await expect(p).rejects.toThrow(/couldn't load the payment window/);
  });

  it("gives up after a timeout instead of waiting forever", async () => {
    const { loadRazorpayScript } = await freshModule();
    const p = loadRazorpay(loadRazorpayScript);
    vi.advanceTimersByTime(20_001);
    await expect(p).rejects.toThrow(/couldn't load the payment window/);
    expect(scripts()).toHaveLength(0);
  });
});

// Attach the rejection handler immediately so the rejection is never "unhandled".
function loadRazorpay(fn: () => Promise<void>) {
  const p = fn();
  p.catch(() => undefined);
  return p;
}

describe("openRazorpayCheckout", () => {
  const request = { keyId: "rzp_test_K", amountPaise: 40621, currency: "INR", razorpayOrderId: "order_X", description: "Order PRM-1" };
  const callbacks = () => ({ onSuccess: vi.fn(), onDismiss: vi.fn(), onFailure: vi.fn() });

  function installFake() {
    const state: { options?: any; open: ReturnType<typeof vi.fn>; handlers: Record<string, (r: any) => void> } = {
      open: vi.fn(), handlers: {},
    };
    window.Razorpay = class {
      constructor(options: unknown) { state.options = options; }
      open = state.open;
      on = (event: string, cb: (r: any) => void) => { state.handlers[event] = cb; };
    } as never;
    return state;
  }

  it("passes the server's values straight through and opens the popup", async () => {
    const { openRazorpayCheckout } = await freshModule();
    const fake = installFake();
    const cb = callbacks();
    openRazorpayCheckout(request, cb);

    expect(fake.open).toHaveBeenCalledTimes(1);
    expect(fake.options).toMatchObject({
      key: "rzp_test_K", amount: 40621, currency: "INR", order_id: "order_X", name: "Pramanika", description: "Order PRM-1",
    });
    expect(fake.options.modal.confirm_close).toBe(true);
    // Only the PUBLIC key id is ever handed over - no secret exists in the browser.
    expect(JSON.stringify(fake.options)).not.toMatch(/secret/i);
  });

  it("forwards success, dismissal and failure", async () => {
    const { openRazorpayCheckout } = await freshModule();
    const fake = installFake();
    const cb = callbacks();
    openRazorpayCheckout(request, cb);

    const paid = { razorpay_order_id: "order_X", razorpay_payment_id: "pay_1", razorpay_signature: "sig" };
    fake.options.handler(paid);
    expect(cb.onSuccess).toHaveBeenCalledWith(paid);

    fake.options.modal.ondismiss();
    expect(cb.onDismiss).toHaveBeenCalledTimes(1);

    fake.handlers["payment.failed"]({ error: { description: "Your card was declined." } });
    expect(cb.onFailure).toHaveBeenCalledWith("Your card was declined.");
  });

  it("reports a failure without a usable description as null", async () => {
    const { openRazorpayCheckout } = await freshModule();
    const fake = installFake();
    const cb = callbacks();
    openRazorpayCheckout(request, cb);
    for (const response of [{}, { error: {} }, { error: { description: "  " } }, undefined]) fake.handlers["payment.failed"](response);
    expect(cb.onFailure.mock.calls.map((c) => c[0])).toEqual([null, null, null, null]);
  });

  it("throws if the SDK is not loaded", async () => {
    const { openRazorpayCheckout } = await freshModule();
    expect(() => openRazorpayCheckout(request, callbacks())).toThrow(/not available/);
  });
});

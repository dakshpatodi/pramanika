/**
 * The only file that touches Razorpay's browser SDK (checkout.js).
 *
 * Everything else works with plain data and callbacks, so tests replace
 * this module and never load a script or open a popup.
 *
 * Security notes:
 *  - the SDK is loaded from Razorpay's own fixed https URL, on demand (only
 *    the checkout page needs it), never from a URL that comes from the server;
 *  - only the PUBLIC key id is ever used here; no secret exists in the browser;
 *  - payment results are passed on untouched and never logged.
 */

export const RAZORPAY_SCRIPT_URL = "https://checkout.razorpay.com/v1/checkout.js";
const SCRIPT_TIMEOUT_MS = 20_000;

/** What Razorpay returns to the page after a successful payment. */
export interface RazorpaySuccessResponse {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
}

export interface RazorpayFailureResponse {
  error?: { code?: string; description?: string; reason?: string };
}

interface RazorpayOptions {
  key: string;
  amount: number;
  currency: string;
  order_id: string;
  name: string;
  description: string;
  handler: (response: RazorpaySuccessResponse) => void;
  modal: { ondismiss: () => void; confirm_close: boolean };
}

interface RazorpayInstance {
  open: () => void;
  on: (event: "payment.failed", callback: (response: RazorpayFailureResponse) => void) => void;
}

type RazorpayConstructor = new (options: RazorpayOptions) => RazorpayInstance;

declare global {
  interface Window {
    Razorpay?: RazorpayConstructor;
  }
}

let loading: Promise<void> | null = null;

/**
 * Makes sure `window.Razorpay` exists. Concurrent callers share one script
 * tag; a failed load is forgotten, so the next attempt tries again instead
 * of replaying the failure forever.
 */
export function loadRazorpayScript(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("The payment window can only open in a browser."));
  if (window.Razorpay) return Promise.resolve();
  if (loading) return loading;

  loading = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    const fail = () => {
      window.clearTimeout(timer);
      script.remove();
      loading = null;
      reject(new Error("We couldn't load the payment window. Check your connection and try again."));
    };
    const timer = window.setTimeout(fail, SCRIPT_TIMEOUT_MS);
    script.src = RAZORPAY_SCRIPT_URL;
    script.async = true;
    script.onload = () => {
      if (window.Razorpay) {
        window.clearTimeout(timer);
        resolve();
      } else {
        fail();
      }
    };
    script.onerror = fail;
    document.head.appendChild(script);
  });
  return loading;
}

export interface CheckoutRequest {
  keyId: string;
  amountPaise: number;
  currency: string;
  razorpayOrderId: string;
  /** Shown in the popup, e.g. "Order PRM-2026-000123". */
  description: string;
}

export interface CheckoutCallbacks {
  /** The customer paid; the response must now be VERIFIED by the backend. */
  onSuccess: (response: RazorpaySuccessResponse) => void;
  /** The customer closed the popup. Not called after a successful payment. */
  onDismiss: () => void;
  /** An attempt failed. The popup usually stays open so the customer can try
   * another method, so this is information, not the end of the flow. */
  onFailure: (description: string | null) => void;
}

/** Opens Razorpay Checkout. Throws if the SDK is not loaded or cannot start. */
export function openRazorpayCheckout(request: CheckoutRequest, callbacks: CheckoutCallbacks): void {
  const Razorpay = typeof window === "undefined" ? undefined : window.Razorpay;
  if (!Razorpay) throw new Error("The payment window is not available. Please try again.");

  const instance = new Razorpay({
    key: request.keyId,
    amount: request.amountPaise,
    currency: request.currency,
    order_id: request.razorpayOrderId,
    name: "Pramanika",
    description: request.description,
    handler: callbacks.onSuccess,
    // confirm_close: closing the popup by accident asks first.
    modal: { ondismiss: callbacks.onDismiss, confirm_close: true },
  });
  instance.on("payment.failed", (response) => {
    const description = response?.error?.description;
    callbacks.onFailure(typeof description === "string" && description.trim() ? description : null);
  });
  instance.open();
}

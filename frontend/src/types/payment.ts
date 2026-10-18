/**
 * Types for the Phase 7 payment endpoints (backend app/schemas/payment.py).
 * Keep in sync manually - there is no shared codegen between the two stacks.
 *
 * What the browser receives is deliberately tiny: it is exactly what
 * Razorpay Checkout needs and nothing secret. The key SECRET and the
 * webhook secret never leave the server.
 */

/** Response of POST /api/orders/{order_id}/payment. Every value was
 * decided by the server; the browser never chooses the amount. */
export interface PaymentIntent {
  order_id: string;
  order_number: string | null;
  razorpay_order_id: string;
  /** The PUBLIC Razorpay key id (rzp_test_... in test mode). */
  razorpay_key_id: string;
  /** Rs 406.21 -> 40621. An integer, as Razorpay Checkout expects. */
  amount_paise: number;
  currency: string;
}

/** The three values Razorpay Checkout hands back after a payment. They are
 * sent to the backend, which checks the signature - the browser's own
 * "it worked" is never trusted. */
export interface PaymentVerificationInput {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

"use client";

import axios from "axios";
import { useCallback, useRef, useState } from "react";

import { getApiErrorMessage } from "@/lib/errors";
import { loadRazorpayScript, openRazorpayCheckout, type RazorpaySuccessResponse } from "@/lib/razorpay";
import * as ordersApi from "@/services/orders";
import * as paymentsApi from "@/services/payments";
import type { Order } from "@/types/order";
import type { PaymentVerificationInput } from "@/types/payment";

/**
 * Where the payment flow stands.
 *
 *   idle           nothing started
 *   starting       loading Razorpay and asking the server for the Razorpay order
 *   awaiting       the Razorpay popup is open
 *   verifying      the customer paid; waiting for the SERVER to confirm
 *   paid           the server confirmed it   <- the only "success"
 *   dismissed      the popup was closed without paying (can retry)
 *   failed         the attempt failed, or could not start (can retry)
 *   verify_failed  the customer may have paid but we couldn't confirm it (can re-check)
 *   closed         the order can't be paid any more: cancelled, expired... (no retry)
 */
export type PaymentPhase =
  | "idle"
  | "starting"
  | "awaiting"
  | "verifying"
  | "paid"
  | "dismissed"
  | "failed"
  | "verify_failed"
  | "closed";

export type PayOutcome = "paid" | "dismissed" | "failed" | "verify_failed" | "closed";

/** The two order fields the flow needs. */
export type PayableOrder = Pick<Order, "id" | "order_number">;

export interface UsePayment {
  /**
   * Opens Razorpay for the order. ALWAYS resolves (never rejects) with how it
   * ended; the message for anything but "paid" is in `error`. While a flow is
   * running, calling it again - a double click - returns the SAME promise.
   */
  pay: (order: PayableOrder) => Promise<PayOutcome>;
  /** After "verify_failed": ask the server again about the payment Razorpay
   * already reported. Does not charge anything and does not reopen the popup. */
  retryVerification: (order: PayableOrder) => Promise<PayOutcome>;
  phase: PaymentPhase;
  error: string | null;
  /** True while a flow is running - disable the buttons. */
  isBusy: boolean;
}

const START_FAILED = "We couldn't start the payment. Nothing was charged. Please try again.";
const VERIFY_FAILED =
  "We couldn't confirm your payment yet. If money left your account, please don't pay again - check your order in a minute.";
const ATTEMPT_FAILED = "The payment didn't go through. Nothing was charged. You can try again.";
const DISMISSED = "The payment window was closed before paying. Your order is saved - you can pay when you're ready.";

function httpStatus(error: unknown): number | undefined {
  return axios.isAxiosError(error) ? error.response?.status : undefined;
}

/** The server's own explanation of an HTTP error, if it sent one. */
function serverMessage(error: unknown): string | null {
  if (!axios.isAxiosError<{ message?: unknown }>(error)) return null;
  const message = error.response?.data?.message;
  return typeof message === "string" && message.trim() ? message : null;
}

function isPaymentVerification(r: Partial<RazorpaySuccessResponse> | null | undefined): r is PaymentVerificationInput {
  return (
    !!r &&
    typeof r.razorpay_order_id === "string" && r.razorpay_order_id !== "" &&
    typeof r.razorpay_payment_id === "string" && r.razorpay_payment_id !== "" &&
    typeof r.razorpay_signature === "string" && r.razorpay_signature !== ""
  );
}

/**
 * Payment flow for an order that already exists (Phase 7).
 *
 *  - The amount always comes from the server's reply; the browser never
 *    sends or decides one.
 *  - Success means ONE thing: the backend verified the payment and returned
 *    the order with `payment_status: "paid"`. Razorpay's popup saying
 *    "success" only starts the verification.
 *  - The whole flow is one in-flight promise, so double clicks (and
 *    React strict-mode double effects) cannot open two popups or verify twice.
 *  - Retrying is always safe: the server reuses the order's open Razorpay
 *    order and refuses a payment on an order that is already paid.
 */
export function usePayment(): UsePayment {
  const [phase, setPhase] = useState<PaymentPhase>("idle");
  const [error, setError] = useState<string | null>(null);

  const inFlight = useRef<Promise<PayOutcome> | null>(null);
  // What Razorpay reported, kept so a failed verification can be repeated
  // without asking the customer to pay again.
  const lastPayment = useRef<PaymentVerificationInput | null>(null);

  const finish = useCallback((outcome: PayOutcome, next: PaymentPhase, message: string | null): PayOutcome => {
    setError(message);
    setPhase(next);
    return outcome;
  }, []);

  // A 409 means "this order cannot take (another) payment": already paid, cancelled,
  // expired, or the money arrived after it closed. All are 409, so ask the server which
  // one it is rather than guessing from the wording.
  const resolveConflict = useCallback(
    async (order: PayableOrder, err: unknown, fallback: string): Promise<PayOutcome> => {
      try {
        const current = await ordersApi.getOrder(order.id);
        if (current.payment_status === "paid") return finish("paid", "paid", null);
      } catch {
        // fall through: show the server's own message
      }
      return finish("closed", "closed", serverMessage(err) ?? fallback);
    },
    [finish]
  );

  const verify = useCallback(
    async (order: PayableOrder, payment: PaymentVerificationInput): Promise<PayOutcome> => {
      setError(null);
      setPhase("verifying");
      try {
        const verified = await paymentsApi.verifyPayment(order.id, payment);
        // Success is the SERVER's word that the order is paid, not a 200.
        if (verified?.payment_status === "paid") {
          lastPayment.current = null;
          return finish("paid", "paid", null);
        }
        return finish("verify_failed", "verify_failed", VERIFY_FAILED);
      } catch (err) {
        // The order cannot take this payment (already paid by another payment, or
        // the money arrived after the order closed): not something to re-check.
        if (httpStatus(err) === 409) {
          lastPayment.current = null;
          return resolveConflict(order, err, "This order can no longer take this payment.");
        }
        // A server reply carries its own explanation (e.g. "could not be verified");
        // anything else (offline, timeout) gets the "don't pay again" guidance.
        return finish("verify_failed", "verify_failed", serverMessage(err) ?? VERIFY_FAILED);
      }
    },
    [finish, resolveConflict]
  );

  const startFailure = useCallback(
    async (order: PayableOrder, err: unknown): Promise<PayOutcome> => {
      const status = httpStatus(err);
      if (status === 409) return resolveConflict(order, err, "This order can no longer be paid.");
      if (status === 404) return finish("closed", "closed", getApiErrorMessage(err, "This order was not found."));
      return finish("failed", "failed", getApiErrorMessage(err, START_FAILED));
    },
    [finish, resolveConflict]
  );

  const run = useCallback((flow: () => Promise<PayOutcome>): Promise<PayOutcome> => {
    if (inFlight.current !== null) return inFlight.current;
    const attempt = flow().finally(() => {
      inFlight.current = null;
    });
    inFlight.current = attempt;
    return attempt;
  }, []);

  const pay = useCallback(
    (order: PayableOrder): Promise<PayOutcome> =>
      run(async () => {
        setError(null);
        setPhase("starting");
        lastPayment.current = null;

        try {
          // Script first: if it can't load there is no point creating a Razorpay order.
          await loadRazorpayScript();
        } catch (err) {
          return finish("failed", "failed", getApiErrorMessage(err, START_FAILED));
        }

        let intent;
        try {
          intent = await paymentsApi.createPayment(order.id);
        } catch (err) {
          return startFailure(order, err);
        }

        return new Promise<PayOutcome>((resolve) => {
          let settled = false;
          let paymentReceived = false;
          let attemptFailed = false;
          let attemptFailure: string | null = null;
          const settle = (outcome: PayOutcome) => {
            if (!settled) {
              settled = true;
              resolve(outcome);
            }
          };

          try {
            openRazorpayCheckout(
              {
                keyId: intent.razorpay_key_id,
                amountPaise: intent.amount_paise,
                currency: intent.currency,
                razorpayOrderId: intent.razorpay_order_id,
                description: intent.order_number ? `Order ${intent.order_number}` : "Your order",
              },
              {
                onSuccess: (response) => {
                  if (paymentReceived) return; // a repeated callback must not verify twice
                  paymentReceived = true;
                  if (!isPaymentVerification(response)) {
                    settle(finish("verify_failed", "verify_failed", VERIFY_FAILED));
                    return;
                  }
                  lastPayment.current = {
                    razorpay_order_id: response.razorpay_order_id,
                    razorpay_payment_id: response.razorpay_payment_id,
                    razorpay_signature: response.razorpay_signature,
                  };
                  void verify(order, lastPayment.current).then(settle);
                },
                onFailure: (description) => {
                  // The popup normally stays open for another try; remember why,
                  // and report it only if the customer then gives up.
                  attemptFailed = true;
                  attemptFailure = description;
                },
                onDismiss: () => {
                  if (paymentReceived) return; // closing after paying must not undo the success
                  settle(
                    attemptFailed
                      ? finish("failed", "failed", `${attemptFailure ?? ""} ${ATTEMPT_FAILED}`.trim())
                      : finish("dismissed", "dismissed", DISMISSED)
                  );
                },
              }
            );
            setPhase("awaiting");
          } catch (err) {
            settle(finish("failed", "failed", getApiErrorMessage(err, START_FAILED)));
          }
        });
      }),
    [finish, run, startFailure, verify]
  );

  const retryVerification = useCallback(
    (order: PayableOrder): Promise<PayOutcome> =>
      run(async () => {
        const payment = lastPayment.current;
        if (payment === null) {
          return finish("failed", "failed", "There is no payment to check. Please try paying again.");
        }
        return verify(order, payment);
      }),
    [finish, run, verify]
  );

  return {
    pay,
    retryVerification,
    phase,
    error,
    isBusy: phase === "starting" || phase === "awaiting" || phase === "verifying",
  };
}

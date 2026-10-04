/**
 * Display helpers for the cart.
 *
 * The cart shows server-calculated amounts that include paise (GST on a
 * Rs.498 subtotal is Rs.24.90), so unlike the catalogue's `formatPrice`
 * (whole rupees) these always show two decimals - otherwise the rows
 * would visibly fail to add up to the total.
 */

const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** 522.9 -> "₹522.90". Formatting only - never used to calculate anything. */
export function formatMoney(amount: number): string {
  return inr.format(amount);
}

/** 0.05 -> "5%", 0.125 -> "12.5%" (avoids float noise like 7.000000000000001%). */
export function formatPercent(rate: number): string {
  return `${Number((rate * 100).toFixed(2))}%`;
}
/**
 * Types mirroring the backend's Phase 5 cart schemas (app/schemas/cart.py).
 * Keep these in sync manually when that file changes - there is no shared
 * codegen between the two stacks.
 *
 * Every amount here was calculated by the server. The frontend only ever
 * displays these numbers; it never derives a subtotal, GST, discount,
 * delivery charge or total of its own.
 */

export interface CartProductSummary {
  id: string;
  name: string;
  slug: string;
  sku: string;
  image_url: string | null;
}

export interface CartItem {
  id: string;
  product: CartProductSummary;
  quantity: number;
  unit_price: number;
  line_subtotal: number;
  /** Stock the customer could still buy of this product - use it to cap
   * the quantity stepper. The server re-checks on every request. */
  available_quantity: number;
  /** Set when this line cannot be bought as it stands (out of stock, more
   * than available, product deactivated). Such lines are excluded from
   * the totals; show the message and let the customer fix or remove them. */
  issue: string | null;
}

export interface CartCoupon {
  code: string;
  description: string | null;
  /** False when the coupon is attached but currently not discounting
   * (expired, cart below its minimum...) - `message` says why. */
  applied: boolean;
  message: string | null;
}

export interface CartTotals {
  subtotal: number;
  discount: number;
  taxable_amount: number;
  gst_rate: number;
  gst: number;
  delivery_charge: number;
  /** How much more product value would make delivery free (0 if already free). */
  amount_for_free_delivery: number;
  total: number;
  currency: string;
}

export interface Cart {
  /** null until the user's first successful add (the cart row is created lazily). */
  id: string | null;
  items: CartItem[];
  /** Total units across all lines - what a navbar badge shows. */
  item_count: number;
  has_issues: boolean;
  coupon: CartCoupon | null;
  totals: CartTotals;
}
# Pramanika — Project Context

## Project

Pramanika is an AI-powered e-commerce platform for cereals, ready mixes, breakfast products, and related food products.

## Current Status

Phase 1 — Project Foundation
Status: COMPLETE

Phase 2 — Authentication
Status: COMPLETE

Phase 3 — Database
Status: COMPLETE

Phase 4 — Product Module
Status: COMPLETE

Phase 5 — Shopping Cart
Status: COMPLETE

Phase 6 — Checkout & Orders
Status: COMPLETE

Phase 7 — Razorpay Integration
Status: COMPLETE (verified in Razorpay TEST MODE on 2026-10-15; see "Phase 7 verification")

Phase 8 — User Dashboard
Status: PLANNED (not started)

Phase 9 — Admin Dashboard
Status: PLANNED

Phase 10 — AI & Advanced Features
Status: PLANNED

Phase 11 — Deployment
Status: PLANNED

## Technology Stack

Frontend:
- Next.js
- React
- TypeScript
- Tailwind CSS
- Vitest
- React Testing Library

Backend:
- Python
- FastAPI
- SQLAlchemy
- Alembic
- httpx (the only package Phase 7 added; used to call the Razorpay REST API)

Database:
- PostgreSQL
- Docker

Authentication:
- JWT access tokens
- JWT refresh tokens
- Refresh-token rotation
- Logout/revocation
- Protected routes
- Login rate limiting

Payments:
- Razorpay (TEST MODE only so far), via Razorpay Checkout in the browser and the Razorpay REST API plus signed webhooks on the server
- No Razorpay SDK package on either side

Development:
- Git
- GitHub
- Postman
- PowerShell

## Git

Main branch:
main

Development branch:
feature/authentication

## Completed Authentication Features

- User registration
- Login
- JWT access token
- JWT refresh token
- Refresh-token rotation
- Logout
- Token revocation
- GET /api/users/me
- Authentication dependencies
- Role-based dependency support
- Login rate limiting
- Frontend login page
- Frontend registration page
- Profile page
- AuthContext
- Protected routes
- Token storage
- Axios API client
- Authentication validation

## Phase 3 — Database

Goal:
Design and implement the e-commerce database.

Entities include:

- Users
- Categories
- Products
- Inventory
- Addresses
- Cart
- Cart Items
- Wishlist
- Wishlist Items
- Orders
- Order Items
- Coupons
- Payments
- Reviews

Important:
- Do not recreate the existing users table.
- Do not break Phase 2 authentication.
- Use the existing SQLAlchemy/Alembic architecture.
- Create migrations for schema changes.

## Phase 4 — Product Module

Status:
COMPLETE

Implemented:
- Product catalogue
- Product listing
- Product detail pages
- Categories
- Search
- Filtering
- Sorting
- Pagination
- Related products
- Product/inventory integration

## Phase 5 — Shopping Cart

Status:
COMPLETE

Implemented:
- Add to cart
- Remove from cart
- Quantity updates
- Coupon application
- GST calculation
- Delivery charge calculation
- Cart pricing
- Stock availability validation
- Cart frontend integration

Important design decisions:
- POST /api/cart/items increments an existing item's quantity.
- PATCH /api/cart/items/{id} replaces the quantity absolutely.
- Cart pricing is calculated server-side.
- Stock validation uses available stock (quantity - reserved_quantity).
- Stock reservation occurs during checkout rather than cart modification.
- Coupon application and pricing are validated server-side.

## Phase 6 — Checkout & Orders

Status:
COMPLETE

Phase 6 contains 8 milestones and has been fully implemented and verified.

### Backend

Implemented:
- Address list API
- Add-address API
- Checkout API
- Order creation
- Order history
- Order detail
- Customer cancellation
- Atomic stock reservation
- Stock reservation release on cancellation
- Coupon usage handling
- Coupon usage restoration on eligible cancellation
- Order item snapshots
- Delivery address snapshots
- Idempotent order creation
- Ownership checks
- Empty-cart validation
- Stale-cart total validation
- Order number generation
- Order/payment status handling

### Address design

Phase 6 supports:
- GET /api/addresses
- POST /api/addresses
- Inline add-address flow during checkout

Address edit/delete/set-default functionality is deferred to Phase 8.

Orders store an immutable delivery-address snapshot.

### Cancellation

Customers can cancel eligible pending orders.

Cancellation:
- is restricted to the order owner
- releases reserved inventory
- restores eligible coupon usage
- is atomic
- is idempotent/safe to repeat

Cancelled orders remain unpaid.

Since Phase 7, cancelling an order also closes any payment attempt still open on it (the payment becomes EXPIRED; the order's own payment_status stays pending).

### Reservation expiry

Automatic unpaid-order reservation expiry was deferred from Phase 6 and is implemented in Phase 7 (30-minute window, background worker plus CLI). See "Phase 7 — Unpaid-order expiry".

### Coupon usage

Phase 6 supports global coupon usage limits through usage_limit/used_count.

Per-user coupon usage limits are not implemented because the current schema does not maintain per-user coupon redemption history.

Coupon usage is updated atomically and restored exactly once for eligible pending-order cancellation (and, since Phase 7, for expiry).

### GST and delivery pricing

Current checkout pricing follows:

subtotal
- discount
= taxable amount

taxable amount
+ GST
+ delivery charge
= final total

The current development configuration uses a 5% GST rate.

GST configuration is stored with order pricing so historical orders retain the rate used when they were created.

Product-specific GST rates are not implemented and would require a separate future design decision.

### Frontend

Implemented:
- Checkout page
- Protected checkout route
- Address selection
- Add-address form
- Address validation
- Order summary
- Place-order flow
- Idempotency handling
- Orders history page
- Order detail page
- Order status display
- Payment status display
- Cancellation flow
- Cart refresh after checkout
- Authenticated Orders navigation link
- Responsive checkout/order UI

### Idempotency behavior

The frontend reuses an idempotency key when the checkout inputs remain unchanged.

A new key is generated when relevant checkout inputs change.

The key is forgotten after successful order placement.

Rapid duplicate submissions are prevented from creating duplicate orders.

### Phase 6 verification (as recorded when Phase 6 closed)

Backend:
- Alembic upgrade completed successfully.
- alembic check reports no new upgrade operations.
- Alembic head at that time: c7d2e91a4b58 (the current head is e4a91c7b3d26, from Phase 7).
- Full backend test suite: 215/215 passed against a disposable PostgreSQL test database.
- Phase 6 smoke test: 39/39 passed.
- Stock reservation/release verified directly in PostgreSQL.
- Coupon usage restoration verified directly in PostgreSQL.
- Cancellation state verified directly in PostgreSQL.

Frontend:
- Vitest: 142/142 tests passed.
- TypeScript check passed.
- Production build passed.
- ESLint passed with no warnings/errors.
- Desktop browser verification passed.
- Mobile browser verification passed at phone-sized viewport.
- Mobile API/CORS configuration was temporarily adjusted for hotspot testing and restored afterward.
- Checkout, order creation, order history, order detail, cancellation, idempotency, ownership, and responsive layout were manually verified.

## Phase 7 — Razorpay Integration

Status:
COMPLETE — verified in Razorpay TEST MODE (see "Phase 7 verification" for exactly what was and was not exercised).

Phase 7 contains 13 milestones (M1–M13). It adds online payment to the Phase 6 orders without changing any Phase 6 rule: stock is still reserved atomically at order creation, available = quantity − reserved_quantity, cancellation of an eligible pending order still releases stock and restores the coupon exactly once, order and address snapshots are immutable, pricing is still subtotal − discount = taxable, taxable + 5% GST + delivery = total, and order creation is still idempotent.

TEST MODE ONLY. Every payment so far used Razorpay test keys (`rzp_test_...`). No live key has been used and no real money has moved. The app refuses to start with a `rzp_live_` key unless APP_ENV=production. No credential is stored in this repository or in this file: values live only in the local `.env` (never committed); `.env.example` holds blank placeholders.

### Architecture

Browser → Pramanika API → Razorpay, and Razorpay → Pramanika API (webhook). The browser never decides that an order is paid.

- Order total is fixed by Phase 6. `POST /api/orders/{id}/payment` has no request body; the amount sent to Razorpay is computed on the server from the stored order (exact Decimal → paise).
- Razorpay Checkout (browser) collects the payment and returns `razorpay_order_id`, `razorpay_payment_id`, `razorpay_signature`.
- `POST /api/orders/{id}/payment/verify` checks the signature, then asks Razorpay for the payment and compares id, order id, amount and currency with what is stored. Only a payment that Razorpay reports as captured pays the order.
- `POST /api/payments/webhook` lets Razorpay tell the server about payments even if the browser closed. Authenticated by signature, not by login.
- A background expiry job releases unpaid orders.
- The frontend treats an order as paid only when the server's order has `payment_status === "paid"`, never because the Razorpay popup said so. `can_pay` and `can_cancel` are the server's verdicts.

Layering (unchanged from earlier phases): router → service → repository; services own commit/rollback; `DomainError` carries `http_status`; responses use `APIResponse[T]`.

Main backend modules (all under `backend/app`):
- `core/payment_config.py` — the only place credentials are read; `public_key_id()` is the only credential-derived value allowed in a response.
- `models/payment.py` — `Payment`, `PaymentWebhookEvent`.
- `services/payment_rules.py` — pure rules: allowed transitions, `payment_block` (may this order be paid now?), `capture_disposition`.
- `services/payment_state.py` — `transition()`, the ONLY writer of `Payment.status`; `close_open_payments`.
- `services/payment_service.py` — create/resume Razorpay order, verify.
- `services/payment_capture.py` — `apply_capture`, shared by verify and webhook.
- `services/payment_webhook_service.py`, `razorpay_webhook.py`, `razorpay_signature.py`, `razorpay_gateway.py`.
- `services/order_expiry_service.py`, `repositories/order_expiry_repository.py`, `jobs/expiry_worker.py`, `jobs/expire_orders.py`.
- Scripts: `scripts/p7_inspect.py` (read-only inspection of an order's payment books), `scripts/p7_webhook_check.py` (webhook wiring probes).

Main frontend modules (under `frontend/src`): `lib/razorpay.ts` (the only file that touches Razorpay's browser SDK, loaded from the fixed https checkout URL), `hooks/usePayment.ts`, `services/payments.ts`, `types/payment.ts`, `components/checkout/PaymentStatusPanel.tsx`, `components/orders/OrderPaymentPanel.tsx`, `hooks/useTimeLeft.ts`, plus changes to the checkout and order pages and `OrderStatusBadge`.

### Environment variables

Names only. Never put values in this file, in git, in chat, or in the frontend.

| Variable | Where | Notes |
|---|---|---|
| RAZORPAY_KEY_ID | backend `.env` | PUBLIC. The only Razorpay value ever sent to the browser (inside the payment response). Must look like `rzp_test_...` or `rzp_live_...`. |
| RAZORPAY_KEY_SECRET | backend `.env` | SERVER ONLY. Stored as a secret type; never returned, logged, or sent to the frontend. |
| RAZORPAY_WEBHOOK_SECRET | backend `.env` | SERVER ONLY. At least 16 characters and different from the key secret, or the app refuses to start. Same value is entered in the Razorpay dashboard webhook settings. |
| RAZORPAY_API_BASE_URL | backend `.env` (optional) | Default Razorpay API URL. Must be https (http only for localhost / 127.0.0.1 mock servers). |
| RAZORPAY_TIMEOUT_SECONDS | backend `.env` (optional) | Default 10, maximum 60. |
| ORDER_PAYMENT_WINDOW_MINUTES | backend `.env` (optional) | Default 30 (1–1440). How long an unpaid order holds stock. |
| ORDER_EXPIRY_WORKER_ENABLED | backend `.env` (optional) | Default true. Set false if the CLI job runs from cron instead. |
| ORDER_EXPIRY_INTERVAL_SECONDS | backend `.env` (optional) | Default 60. |
| ORDER_EXPIRY_BATCH_SIZE | backend `.env` (optional) | Default 50 (1–500). |

The frontend reads only `NEXT_PUBLIC_API_URL` (unchanged). It has no Razorpay environment variable: the key id arrives in the API response.

### Payments table (Phase 3 table, extended by migration e4a91c7b3d26)

`payments` — one row per Razorpay order (one payment attempt set). An order may have several rows (a failed attempt, then a successful retry). Columns: id, order_id, payment_gateway ("razorpay"), gateway_order_id, gateway_payment_id, gateway_signature, amount, currency, status, failure_reason, paid_at, refund_required, created_at, updated_at.

Database guarantees (CHECKs and unique indexes):
- amount > 0; currency is 3 letters; a Razorpay row has a gateway_order_id
- paid_at is set exactly when status is captured or refunded; those rows must have a gateway_payment_id
- refund_required only on captured rows
- gateway_order_id unique; gateway_payment_id unique
- at most ONE open (initiated/authorized) payment per order — the database-level guarantee behind idempotent payment creation

`payment_webhook_events` — one row per processed Razorpay webhook delivery, unique on event_id, storing identifiers and the outcome only (never the payload, which carries customer email/phone).

`orders` gained: `expires_at`, `cancellation_reason` (`customer` | `expired`, set exactly when status is cancelled), and the partial index `ix_orders_open_expires_at` for the expiry sweep.

Only gateway references are stored. No card data ever reaches this system.

### Payment lifecycle and state machine

Payment status (per attempt): initiated → authorized → captured → refunded; failed and expired are not final.

Allowed moves (`payment_rules.ALLOWED_TRANSITIONS`, enforced in `payment_state.transition`):
- initiated → authorized, captured, failed, expired
- authorized → captured, failed, expired
- failed → captured (a retry or late success can still capture)
- expired → captured (money arrived after the order closed: recorded and flagged for refund)
- captured → refunded only. A late failure, a cancel or the expiry job can never move a captured payment.
- refunded → nothing

Order lifecycle with payment:
1. Place order (Phase 6): status pending, payment_status pending, stock reserved, `expires_at` = creation + 30 minutes.
2. Pay: `POST /api/orders/{id}/payment` creates (or resumes) one Razorpay order; Checkout opens; on success the browser calls verify.
3. Captured while the order is alive: order status confirmed, payment_status paid, reservation CONSUMED (units are sold, coupon use stays).
4. A failed attempt leaves the order pending and payable; the customer retries on the SAME order (a new payment row), and the order can still expire.
5. Cancel (customer) or expiry: order cancelled (reason customer / expired), stock released once, coupon restored once, open payment attempt closed as EXPIRED.
6. Late payment: money captured after the order closed is recorded as captured with `refund_required = true`. The order stays cancelled/expired and is never revived (its stock may already belong to someone else). The refund is manual in the Razorpay dashboard. There is no refund API call and no automatic alert.

Order payment-state summary shown to customers: Paid; Payment pending; Payment window closed (past `expires_at`, expiry job not yet run); Expired; Cancelled.

### Endpoints

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/api/orders/{id}/payment` | login, owner only | No body. 201 when a Razorpay order was created, 200 when the open one is resumed. Returns order id/number, Razorpay order id, PUBLIC key id, amount in paise, currency. `Cache-Control: no-store`. Errors: 404 not your order, 409 not payable / already paid, 502 Razorpay failed, 503 payments not configured. |
| POST | `/api/orders/{id}/payment/verify` | login, owner only | Body: razorpay_order_id, razorpay_payment_id, razorpay_signature (format-checked). Returns the order as it now stands; only `payment_status = "paid"` means confirmed (an authorized-but-not-captured payment answers 200 with the order still unpaid). Errors: 400 one generic message for any verification failure, 404, 409 already paid by another payment or late payment (recorded first), 502 Razorpay could not be asked. |
| POST | `/api/payments/webhook` | signature (`X-Razorpay-Signature`), no login | Events handled: payment.authorized, payment.captured, payment.failed, order.paid. 2xx for every outcome a retry cannot improve (including ignored events); 400 bad signature or unreadable body; 413 body over 256 KiB; 503 no webhook secret (Razorpay retries). |

Phase 6 order endpoints are extended, not replaced: order responses gain `can_pay`, `expires_at`, `cancellation_reason` and `payment { last_attempt, refund_pending }`; order summaries gain `can_pay`, `expires_at`, `cancellation_reason`. No secret, signature, gateway id or amount from Razorpay appears in any order response.

### Idempotency

- Payment creation: the order row is locked; an open payment is returned instead of creating another; the unique "one open payment per order" index backs this up if two requests race.
- Verify: an already-recorded payment is answered from the database and changes nothing; repeating the call is safe.
- Webhook: the event id (`X-Razorpay-Event-Id`, or a hash of the body if absent) is claimed with `INSERT ... ON CONFLICT DO NOTHING` in the same transaction as the state change. A repeat delivery finds it taken and does nothing; a failure rolls back the claim, so Razorpay's retry starts clean.
- Capture is applied by one shared function for verify and webhook, so they cannot disagree. Lock order is always order → payment → inventory (no deadlocks).
- Expiry and cancel are compare-and-set updates under the order lock: stock is released at most once, the coupon restored at most once, and a paid order is never expired.
- Webhook outcomes recorded: paid, late_payment, authorized, failed, already_recorded, ignored_stale, ignored_event, ignored_unknown, rejected_mismatch, manual_review, duplicate.

### Phase 7 — Unpaid-order expiry

- An unpaid order keeps its stock for `ORDER_PAYMENT_WINDOW_MINUTES` (30). Then it becomes cancelled with reason `expired` (the UI shows "Expired").
- One asyncio worker runs inside the web server (no Redis, no Celery) every `ORDER_EXPIRY_INTERVAL_SECONDS`. `python -m app.jobs.expire_orders` (optional `--loop`) does the same from the command line.
- Per order, one transaction: lock with SKIP LOCKED → compare-and-set expire → close the open payment attempt → restore the coupon once → release stock once → commit. A failure rolls that order back; one bad order never blocks the others; several workers can run at once.
- The Razorpay order itself cannot be cancelled by this job; if the customer still pays there later, the late-payment path flags it for refund.
- `can_pay` becomes false the moment the deadline passes, even before the job has run.

### Security rules (must hold in all later phases)

- RAZORPAY_KEY_SECRET and RAZORPAY_WEBHOOK_SECRET never leave the server: not in any API response, log, error message, frontend file or build output. Only RAZORPAY_KEY_ID may reach the browser.
- Never commit or hardcode credentials; `.env.example` has placeholders only; never paste secrets in chat or tickets. Use TEST MODE until a deliberate, separate go-live step.
- Never trust the amount or the success status from the browser. The amount comes from the stored order; success comes from a verified signature plus Razorpay's own record (verify) or a signed webhook.
- Signatures: checkout HMAC over `order_id|payment_id`; webhook HMAC over the exact raw body bytes; constant-time comparison. The webhook body is size-capped before the signature check.
- Webhook is authenticated by its secret alone, so the secret must be long and random (minimum 16 characters, enforced at startup).
- All payment writes go through `payment_state.transition` inside database transactions; a captured payment can only become refunded.
- Logs carry ids, statuses and short Razorpay error codes only — never bodies, signatures, secrets, emails or phone numbers.
- Settings validation errors hide the raw input so a rejected secret is never printed.
- Tests enforce this: a secret-hygiene test (no secret in responses, logs or source) and a frontend test that scans the source for secrets.
- A code review (M12) is recorded in `SECURITY_REVIEW_M12.md`. It is a code review, not a penetration test.

### Operating notes and known limitations

- Refunds are manual. A paid-after-close payment shows as `refund_required`. Find them with `python -m scripts.p7_inspect --latest N --check` (look for `** REFUND REQUIRED **`) or `SELECT ... FROM payments WHERE refund_required`. A second payment id captured on an already-paid Razorpay order is recorded only as a webhook event with outcome `manual_review`; the customer is not told. The `refunded` status exists in the state machine, but nothing in the app moves a payment to it yet.
- The code never sends a capture instruction; it relies on the Razorpay dashboard being set to automatic capture. With manual capture, payments would stay "authorized" and orders would expire.
- Local webhook testing needs a public https tunnel (for example ngrok or cloudflared) pointing at `/api/payments/webhook`.
- No rate limiting on payment endpoints and default database pool sizes: put rate limiting at the reverse proxy and set the pool explicitly before production. Create-order and verify call Razorpay inside an open transaction by design.
- If money is captured at Razorpay but booking it fails (for example inventory books out of balance), the transaction rolls back and a CRITICAL log line "CAPTURED MONEY NOT RECORDED" names the order and payment. Any future stock editing (Phase 8+) must refuse to set quantity below reserved_quantity.
- `payment_webhook_events` has no purge (identifiers only). Add a periodic cleanup (for example rows older than 90 days) when volume warrants.
- A failed first attempt lets the customer open a second Razorpay order while the first popup may still be open. If both are paid, the second is flagged `refund_required` and is never double-credited.
- Not implemented (outside Phase 7): refund API, payment emails/notifications, per-user coupon limits, shipping/fulfilment after confirmation, address edit/delete. Those belong to later phases.
- Older Phase 6 behaviour unchanged: per-user coupon limits are still not implemented; GST is still a flat 5%.

### Phase 7 verification

Verified on the developer's machine on 2026-10-15:

Backend:
- Full backend suite: 761 tests, OK (215 from earlier phases + 546 in the Phase 7 test files) against a disposable PostgreSQL test database.
- alembic check: "No new upgrade operations detected."
- alembic current / alembic heads: e4a91c7b3d26 (head), a single head.
- Phase 6 smoke test (phase6_smoke_test.ps1): 39/39 passed — Phase 6 behaviour intact.

Frontend:
- `npx tsc --noEmit`: clean.
- Vitest: 20 files, 273 tests passed (142 at the close of Phase 6).
- `npm run lint`: no warnings or errors.
- `npm run build`: succeeded (13/13 pages; `/orders/[id]` is dynamic).

Browser, Razorpay TEST MODE (checklist in `README_M11.md`, results in `RESULTS_M11.md`, inspected with `p7_inspect`):
- Webhook wiring check, locally and through a tunnel: pass.
- Happy path with browser verification: pass.
- Popup closed, then paid later from the order page: pass.
- Declined payment, then a successful retry on the same order: pass.
- Verify blocked, webhook alone pays the order: pass.
- Customer cancel before paying (stock and coupon restored once): pass.
- Expiry (page shows Expired; stock and coupon restored): pass.
- Late payment after the order closed (refund flag set, order stays closed): pass.
- No secrets in the `/payment` response, none in the built frontend files, `.env` not tracked and no keys in the git diff: pass.
- Real webhook outcomes observed: paid, already_recorded, ignored_stale, late_payment (plus authorized and failed events).

NOT exercised (be honest about these):
- Manual refund in the Razorpay dashboard (scenario 7b) and a duplicate webhook delivery (scenario 8) were not done in the browser run. Duplicate delivery and the other outcomes (duplicate, rejected_mismatch, manual_review, ignored_unknown) are covered by automated tests only.
- The capture setting was not written on the results sheet; payments did reach captured without manual action.
- No live-mode payment, no real money, no load or penetration testing.

### Notes for later phases

- Phase 8 (User Dashboard) must not weaken any rule above. Any admin or dashboard stock editing must refuse quantity < reserved_quantity.
- Phase 9 (Admin Dashboard) is the natural home for a refund workflow (list `refund_required` payments, call the refund API, move captured → refunded) and for shipping/fulfilment states.
- Going live is a separate, deliberate step: live keys, `APP_ENV=production`, a real public webhook URL, a long random webhook secret, rate limiting, and an end-to-end test with the live dashboard in a controlled way.

## Original Roadmap

Phase 3 — Database
Phase 4 — Product Module
Phase 5 — Shopping Cart
Phase 6 — Checkout & Orders
Phase 7 — Razorpay Integration
Phase 8 — User Dashboard
Phase 9 — Admin Dashboard
Phase 10 — AI & Advanced Features
Phase 11 — Deployment

## Planned AI Features

Phase 10 will eventually include:

- AI shopping assistant
- RAG
- Semantic product search
- Product recommendations
- Personalized recommendations
- Frequently bought together

Potential AI stack:

- LLM
- Embeddings
- pgvector
- RAG pipeline

Do not implement these before the appropriate phase unless explicitly requested.

## Development Rules

1. Inspect existing code before modifying it.
2. Do not rewrite working functionality unnecessarily.
3. Do not delete existing authentication data.
4. Do not use destructive database resets.
5. Create migrations for database changes.
6. Test changes before committing.
7. Keep phases separate.
8. Explain architectural decisions.
9. Never assume the existing schema — inspect it first.
10. Maintain compatibility with the existing project structure.
11. Do not commit unrelated working-tree changes.
12. Do not begin the next phase until the current phase has been verified and closed.
13. Never expose or commit payment secrets; use Razorpay TEST MODE until a deliberate go-live.

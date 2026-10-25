"""
Domain-level exceptions raised by the service layer.

These are plain Python exceptions with zero FastAPI/HTTP knowledge - the
service layer (app/services/) raises them, and a single generic handler
registered in main.py translates them into HTTP responses using each
exception's own `http_status`. Adding a new domain error later never
requires touching main.py.
"""


class DomainError(Exception):
    """Base class for all business-rule violations."""

    http_status: int = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class DuplicateEmailError(DomainError):
    http_status = 409

    def __init__(self, email: str):
        super().__init__(f"An account with email '{email}' already exists.")


class DuplicatePhoneError(DomainError):
    http_status = 409

    def __init__(self, phone_number: str):
        super().__init__(f"An account with phone number '{phone_number}' already exists.")


class InvalidCredentialsError(DomainError):
    http_status = 401

    def __init__(self):
        super().__init__("Incorrect email or password.")


class AccountInactiveError(DomainError):
    http_status = 403

    def __init__(self):
        super().__init__("This account has been deactivated.")


class InvalidRefreshTokenError(DomainError):
    http_status = 401

    def __init__(self):
        super().__init__("Refresh token is invalid, expired, or has already been used.")


class ProductNotFoundError(DomainError):
    http_status = 404

    def __init__(self, identifier: str):
        super().__init__(f"Product '{identifier}' was not found.")


class CategoryNotFoundError(DomainError):
    http_status = 404

    def __init__(self, slug: str):
        super().__init__(f"Category '{slug}' was not found.")


class CartItemNotFoundError(DomainError):
    """Raised both when the item id does not exist and when it belongs to
    someone else's cart - deliberately the same error, so the endpoint
    cannot be used to probe which item ids exist."""

    http_status = 404

    def __init__(self):
        super().__init__("Cart item was not found.")


class ProductUnavailableError(DomainError):
    """The product does not exist or has been deactivated. One error for
    both, matching the catalogue, which hides inactive products entirely."""

    http_status = 404

    def __init__(self):
        super().__init__("This product is not available.")


class InsufficientStockError(DomainError):
    http_status = 409

    def __init__(self, available: int, in_cart: int = 0):
        if available <= 0:
            message = "This product is currently out of stock."
        elif in_cart > 0:
            message = (
                f"You already have {in_cart} in your cart - "
                f"only {available} {'unit is' if available == 1 else 'units are'} available in total."
            )
        else:
            message = f"Only {available} {'unit is' if available == 1 else 'units are'} available in stock."
        super().__init__(message)
        self.available = available


class InvalidCouponError(DomainError):
    http_status = 400

    def __init__(self, message: str = "Invalid coupon code."):
        super().__init__(message)


# --- Phase 6: Checkout and orders ------------------------------------

class EmptyCartError(DomainError):
    http_status = 400

    def __init__(self):
        super().__init__("Your cart is empty. Add something before checking out.")


class AddressNotFoundError(DomainError):
    """The address does not exist OR belongs to another customer - one
    error for both, so the endpoint can't be used to probe address ids."""

    http_status = 404

    def __init__(self):
        super().__init__("Delivery address was not found.")


class CartIssuesError(DomainError):
    """At least one cart line cannot be bought as it stands (out of stock,
    more than is available, product deactivated). The cart page already
    shows which; the message names the first one."""

    http_status = 409

    def __init__(self, message: str):
        super().__init__(message)


class CartChangedError(DomainError):
    """The total the customer saw is no longer the total the server
    calculates (a price, coupon or delivery rule changed in between).
    Nothing was ordered; the customer must review and confirm again."""

    http_status = 409

    def __init__(self):
        super().__init__("Prices in your cart have changed. Please review the updated total and try again.")


class IdempotencyKeyReusedError(DomainError):
    http_status = 409

    def __init__(self):
        super().__init__("This Idempotency-Key was already used for a different checkout request.")


class OrderNotFoundError(DomainError):
    """Not found OR not yours - the same error for both."""

    http_status = 404

    def __init__(self):
        super().__init__("Order was not found.")


class OrderNotCancellableError(DomainError):
    http_status = 409

    def __init__(self, status: str):
        super().__init__(f"An order that is {status} can no longer be cancelled.")


class PaymentsNotConfiguredError(DomainError):
    """Razorpay credentials are missing on the server. The message is
    deliberately generic - it must not tell a customer (or an attacker)
    which setting is absent; the details go to the server log."""

    http_status = 503

    def __init__(self):
        super().__init__("Online payments are not available right now. Please try again later.")

# --- Phase 7: payments -----------------------------------------------

class OrderNotPayableError(DomainError):
    """The order cannot be paid for right now (cancelled, expired, stock no
    longer held, nothing to pay...). The message says why in customer words."""

    http_status = 409

    def __init__(self, message: str = "This order can no longer be paid."):
        super().__init__(message)


class OrderAlreadyPaidError(DomainError):
    http_status = 409

    def __init__(self):
        super().__init__("This order has already been paid.")


class PaymentGatewayError(DomainError):
    """Razorpay could not be reached or refused the request. 502 = "the
    server we depend on failed", and the message is deliberately generic -
    the real reason (which never contains a secret) goes to the server log."""

    http_status = 502

    def __init__(self):
        super().__init__("We could not start the payment. Nothing was charged. Please try again in a moment.")

class PaymentVerificationError(DomainError):
    """The payment could not be verified: bad signature, a Razorpay order that
    is not this order's, or Razorpay does not confirm the payment. One generic
    message for every cause, so the endpoint cannot be used to probe which
    check failed."""

    http_status = 400

    def __init__(self):
        super().__init__("We could not verify this payment.")


class PaymentVerificationUnavailableError(DomainError):
    """Razorpay could not be asked right now. Unlike PaymentGatewayError this
    is about a payment that MAY have been made, so it must not say nothing was
    charged."""

    http_status = 502

    def __init__(self):
        super().__init__(
            "We couldn't confirm your payment right now. If money left your account, "
            "please don't pay again - check your order in a minute."
        )


class LatePaymentError(DomainError):
    """The money arrived after the order had been cancelled or expired (or the
    order was already paid by another payment). It is recorded and flagged for
    a refund; the order is NOT revived."""

    http_status = 409

    def __init__(self):
        super().__init__(
            "Your payment was received after this order had been closed, so the order was not placed. "
            "The amount will be refunded to you."
        )

class WebhookSignatureError(DomainError):
    """A webhook whose signature does not match (400). Razorpay never sees why."""

    http_status = 400

    def __init__(self):
        super().__init__("Invalid webhook signature.")


class WebhookPayloadError(DomainError):
    """A correctly signed webhook whose body cannot be read (400)."""

    http_status = 400

    def __init__(self, message: str = "Invalid webhook payload."):
        super().__init__(message)


class WebhookTooLargeError(DomainError):
    http_status = 413

    def __init__(self):
        super().__init__("Webhook payload is too large.")


class AddressLimitReachedError(DomainError):
    """The customer already has the maximum number of saved addresses (409).
    The list endpoint is never unbounded: delete one to add another."""

    http_status = 409

    def __init__(self, limit: int):
        super().__init__(
            f"You can save up to {limit} addresses. Delete one you no longer use to add another."
        )


class WishlistFullError(DomainError):
    """The wishlist already holds the maximum number of products (409).
    Like saved addresses, the list is bounded: remove one to add another."""

    http_status = 409

    def __init__(self, limit: int):
        super().__init__(
            f"Your wishlist can hold up to {limit} products. Remove one you no longer want to add another."
        )

class InvoiceNotAvailableError(DomainError):
    """An invoice exists only for an order that has been paid (409). A missing
    or someone else's order is a plain OrderNotFoundError (404) instead."""

    http_status = 409

    def __init__(self):
        super().__init__("An invoice is available once the order has been paid.")

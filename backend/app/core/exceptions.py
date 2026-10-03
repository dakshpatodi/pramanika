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
    """Raised for BOTH "no such email" and "wrong password".

    Deliberately the same exception, message, and status for both cases -
    see Milestone 4 notes: if the two cases differed, the login endpoint
    could be used to check which emails are registered (user enumeration).
    """

    http_status = 401

    def __init__(self):
        super().__init__("Incorrect email or password.")


class AccountInactiveError(DomainError):
    """The credentials were correct, but the account has been deactivated
    (`is_active=False`). Distinct from InvalidCredentialsError on purpose:
    this is not a secret worth hiding - a deactivated user knows they have
    an account, so a specific message here isn't an enumeration risk."""

    http_status = 403

    def __init__(self):
        super().__init__("This account has been deactivated.")


class InvalidRefreshTokenError(DomainError):
    """Covers every way a refresh token can fail: malformed, wrong `type`
    claim, expired, already revoked (used once already, or logged out),
    or pointing at a user that no longer exists / is inactive. Collapsed
    into one message for the same reason InvalidCredentialsError is
    collapsed - the client doesn't need to know which specific case hit,
    it just needs to log the user out and prompt a fresh login."""

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
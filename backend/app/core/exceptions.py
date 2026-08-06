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
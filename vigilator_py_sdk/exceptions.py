"""Exceptions raised by the Vigilator SDK."""

from __future__ import annotations

from typing import Any


class VigilatorError(Exception):
    """Base class for all errors raised by the Vigilator SDK."""


class VigilatorConnectionError(VigilatorError):
    """Raised when the API could not be reached (network failure, timeout, etc.)."""


class APIError(VigilatorError):
    """Raised when the API responds with an error status code.

    Attributes:
        status: HTTP status code of the response.
        code: Machine-readable error code returned by the API.
        message: Human-readable error message returned by the API.
        data: Additional structured error details, if any.

    """

    def __init__(self, status: int, code: str, message: str, data: Any | None = None):
        """Initialize the error with the API's status, code, message and details."""
        self.status = status
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"{code} ({status}): {message}")


class UsageLimitError(APIError):
    """Raised on 402 USAGE_LIMIT_REACHED: the organisation's usage quota is exhausted."""


class PlanRequiredError(APIError):
    """Raised on 402 PLAN_REQUIRED: the feature requires a paid plan."""


class AddonRequiredError(APIError):
    """Raised on 402 ADDON_REQUIRED: the feature requires an add-on."""


class WorkspaceLimitError(APIError):
    """Raised on 403 WORKSPACE_LIMIT_REACHED: the workspace limit has been reached."""


ERROR_CLASSES: dict[str, type[APIError]] = {
    "USAGE_LIMIT_REACHED": UsageLimitError,
    "PLAN_REQUIRED": PlanRequiredError,
    "ADDON_REQUIRED": AddonRequiredError,
    "WORKSPACE_LIMIT_REACHED": WorkspaceLimitError,
}

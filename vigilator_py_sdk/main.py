"""Client SDK for interacting with the Vigilator API."""

from __future__ import annotations

import httpx
from httpx_retries import Retry, RetryTransport

from vigilator_py_sdk.exceptions import ERROR_CLASSES, APIError, VigilatorConnectionError
from vigilator_py_sdk.models import InterruptsPostRequest, InterruptsPostResponse

# POST is included so create_interrupt is retried too; retries only fire on
# 429/502/503/504, where the request is normally not processed by the server.
_RETRY_METHODS = ["HEAD", "GET", "PUT", "POST", "DELETE", "OPTIONS", "TRACE"]


def _error_from_response(response: httpx.Response) -> APIError:
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    code = body.get("code", "UNKNOWN")
    message = body.get("message") or response.reason_phrase
    error_class = ERROR_CLASSES.get(code, APIError)
    return error_class(response.status_code, code, message, body.get("data"))


class Client:
    """Handles authenticated requests for the Vigilator API.

    Attributes:
        key: API key associated with desired organisation.

    """

    def __init__(
        self,
        key: str,
        base_url: str = "https://api.vigilator.dev",
        retries: int = 5,
        backoff_factor: float = 0.5,
        timeout: httpx.Timeout | float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ):
        """Initialize the client with an API key.

        Args:
            key: API key associated with desired organisation.
            base_url: Base URL of the Vigilator API.
            retries: How often to retry requests that fail with 429/502/503/504
                or a connection error.
            backoff_factor: Multiplier for the exponential delay between retries.
            timeout: Timeout in seconds (or an httpx.Timeout) for requests.
            transport: Underlying transport to wrap with retry behaviour;
                mainly useful for testing with httpx.MockTransport.

        """
        self.key = key
        retry = Retry(total=retries, backoff_factor=backoff_factor, allowed_methods=_RETRY_METHODS)
        self.client = httpx.Client(
            headers={"x-api-key": key},
            base_url=base_url,
            timeout=timeout,
            transport=RetryTransport(transport=transport, retry=retry),
        )

    def create_interrupt(self, interrupt: InterruptsPostRequest) -> InterruptsPostResponse:
        """Create an interrupt.

        Args:
            interrupt: The interrupt to create.

        Returns:
            The created interrupt as returned by the API.

        Raises:
            APIError: The API responded with an error status code. Quota errors
                raise the more specific UsageLimitError, PlanRequiredError,
                AddonRequiredError or WorkspaceLimitError subclasses.
            VigilatorConnectionError: The API could not be reached.

        """
        try:
            response = self.client.post("api/interrupts", json=interrupt.model_dump(mode="json", exclude_none=True))
        except httpx.HTTPError as e:
            raise VigilatorConnectionError(str(e)) from e
        if response.is_success:
            return InterruptsPostResponse.model_validate(response.json())
        raise _error_from_response(response)

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self.client.close()

    def __enter__(self) -> Client:
        """Return the client for use as a context manager."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the client on context exit."""
        self.close()

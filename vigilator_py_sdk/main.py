"""Client SDK for interacting with the Vigilator API."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from urllib.parse import quote

import httpx
from httpx_retries import Retry, RetryTransport

from vigilator_py_sdk.exceptions import ERROR_CLASSES, APIError, VigilatorConnectionError
from vigilator_py_sdk.models import (
    InterruptsIdGetResponse,
    InterruptsPostRequest,
    InterruptsPostResponse,
    Message,
    SessionsIdEndPostResponse,
    SessionsIdMessagesPostRequest,
    SessionsIdMessagesPostResponse,
    SessionsPostRequest,
    SessionsPostResponse,
)

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


def _dump_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
    """Serialize messages for a request body, omitting unset optional fields."""
    return [message.model_dump(mode="json", exclude_none=True) for message in messages]


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

    def _request(self, method: str, path: str, json: Any | None = None) -> Any:
        """Send a request and return the decoded JSON body of a successful response.

        Raises:
            APIError: The API responded with an error status code.
            VigilatorConnectionError: The API could not be reached.

        """
        try:
            response = self.client.request(method, path, json=json)
        except httpx.HTTPError as e:
            raise VigilatorConnectionError(str(e)) from e
        if response.is_success:
            return response.json()
        raise _error_from_response(response)

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
        body = self._request("POST", "api/interrupts", json=interrupt.model_dump(mode="json", exclude_none=True))
        return InterruptsPostResponse.model_validate(body)

    def get_interrupt(self, interrupt_id: str) -> InterruptsIdGetResponse:
        """Fetch a single interrupt by id, including decisions on its action requests.

        Poll this after opening an interrupt to learn the outcome: `answered`
        flips true once every action request is decided.

        Args:
            interrupt_id: Id of the interrupt to fetch.

        Returns:
            The interrupt as returned by the API.

        Raises:
            APIError: The API responded with an error status code. A missing
                interrupt raises the more specific NotFoundError subclass.
            VigilatorConnectionError: The API could not be reached.

        """
        body = self._request("GET", f"api/interrupts/{quote(interrupt_id, safe='')}")
        return InterruptsIdGetResponse.model_validate(body)

    def start_session(
        self,
        name: str,
        *,
        external_id: str | None = None,
        messages: Sequence[Message] | None = None,
    ) -> SessionsPostResponse:
        """Start a live agent session, so its conversation can be watched in Live View.

        Call this when an agent run starts, stream the conversation with
        `append_session_messages` as it progresses, and close it with
        `end_session` when the run completes. A session that goes quiet for
        longer than the organisation's session timeout is ended automatically.

        Args:
            name: The agent's name as shown in Live View, e.g. "billing-agent".
            external_id: Your own correlation id for the run, e.g. the run or
                thread id in your agent framework.
            messages: The opening context, e.g. the user prompt that started
                the run. At most 200 messages.

        Returns:
            The created session as returned by the API; keep its `id` for the
            append and end calls.

        Raises:
            APIError: The API responded with an error status code. Quota errors
                raise the more specific UsageLimitError, PlanRequiredError,
                AddonRequiredError or WorkspaceLimitError subclasses.
            VigilatorConnectionError: The API could not be reached.

        """
        # Validating through the generated request model gives client-side
        # checks (name length, message cap) before the request is sent.
        request = SessionsPostRequest.model_validate({
            "name": name,
            "externalId": external_id,
            "messages": _dump_messages(messages) if messages is not None else None,
        })
        body = self._request("POST", "api/sessions", json=request.model_dump(mode="json", exclude_none=True))
        return SessionsPostResponse.model_validate(body)

    def append_session_messages(self, session_id: str, messages: Sequence[Message]) -> SessionsIdMessagesPostResponse:
        """Append messages to a running session, so watchers see the transcript grow live.

        Args:
            session_id: Id of the session, as returned by `start_session`.
            messages: The messages to append, in conversation order. Between 1
                and 200 messages per call.

        Returns:
            The session as returned by the API, including its most recent
            messages and the total `messageCount`.

        Raises:
            APIError: The API responded with an error status code. A missing
                session raises the more specific NotFoundError subclass; a
                session that has already ended is a 409 CONFLICT.
            VigilatorConnectionError: The API could not be reached.

        """
        request = SessionsIdMessagesPostRequest.model_validate({"messages": _dump_messages(messages)})
        body = self._request(
            "POST",
            f"api/sessions/{quote(session_id, safe='')}/messages",
            json=request.model_dump(mode="json", exclude_none=True),
        )
        return SessionsIdMessagesPostResponse.model_validate(body)

    def end_session(self, session_id: str) -> SessionsIdEndPostResponse:
        """End a live agent session when the run completes.

        Ending an already-ended session is a no-op that returns the current
        state, so it is safe to retry.

        Args:
            session_id: Id of the session, as returned by `start_session`.

        Returns:
            The ended session as returned by the API.

        Raises:
            APIError: The API responded with an error status code. A missing
                session raises the more specific NotFoundError subclass.
            VigilatorConnectionError: The API could not be reached.

        """
        body = self._request("POST", f"api/sessions/{quote(session_id, safe='')}/end")
        return SessionsIdEndPostResponse.model_validate(body)

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self.client.close()

    def __enter__(self) -> Client:
        """Return the client for use as a context manager."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the client on context exit."""
        self.close()

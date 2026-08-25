"""Verify and dispatch webhook events delivered by Vigilator.

Vigilator delivers webhooks through Svix, which signs every delivery with the
``svix-id``, ``svix-timestamp`` and ``svix-signature`` headers using the
Standard Webhooks scheme (HMAC-SHA256 over ``{id}.{timestamp}.{raw_body}``).
The event payload models here mirror Vigilator's published payload contract;
they are hand-written on purpose, as webhook payloads are not part of the
OpenAPI spec that ``models.py`` is generated from.
"""

from __future__ import annotations

import base64
import hmac
import json
import time
from collections.abc import Callable, Mapping
from enum import Enum
from typing import Any, Literal, Union

from pydantic import AwareDatetime, BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from vigilator_py_sdk.exceptions import WebhookVerificationError

DEFAULT_TOLERANCE = 300.0
"""Maximum allowed clock skew (either direction) for ``svix-timestamp``, in seconds."""

_WHSEC_PREFIX = "whsec_"
_SIGNATURE_VERSION = "v1"

_ERR_BAD_WHSEC = "The signing secret is not valid: expected 'whsec_' followed by base64."
_ERR_MISSING_HEADERS = "Missing svix-id, svix-timestamp or svix-signature header."
_ERR_BAD_TIMESTAMP = "The svix-timestamp header is not a Unix timestamp."
_ERR_TIMESTAMP_TOO_OLD = "The svix-timestamp header is too old; possible replay."
_ERR_TIMESTAMP_TOO_NEW = "The svix-timestamp header is in the future."
_ERR_BODY_NOT_UTF8 = "The request body is not valid UTF-8."
_ERR_NO_MATCHING_SIGNATURE = "No signature in svix-signature matches the request body."
_ERR_BODY_NOT_JSON = "The verified request body is not valid JSON."


class Decision(str, Enum):
    """A reviewer decision on an action request."""

    approve = "approve"
    edit = "edit"
    reject = "reject"
    respond = "respond"


class _PayloadModel(BaseModel):
    """Base for payload models: camelCase JSON keys, snake_case attributes."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CreatedActionRequest(_PayloadModel):
    """An action the agent proposed on a newly created interrupt."""

    name: str
    args: dict[str, Any]
    allowed_decisions: list[Decision]


class InterruptCreatedData(_PayloadModel):
    """Payload of an ``interrupt.created`` event."""

    id: str
    external_id: str | None
    title: str
    description: str
    classification: str | None
    action_requests: list[CreatedActionRequest]


class InterruptCreatedEvent(_PayloadModel):
    """An agent opened a new interrupt."""

    type: Literal["interrupt.created"]
    timestamp: AwareDatetime
    data: InterruptCreatedData


class AnsweredActionRequest(_PayloadModel):
    """The reviewer's decision on one action request of an answered interrupt."""

    name: str
    decision: Decision | None
    decided_by_name: str | None
    edited_args: dict[str, Any] | None
    """Edit only: the reviewer's replacement for the proposed args."""
    response_text: str | None
    """Respond: the answer. Reject: an optional reason."""


class InterruptAnsweredData(_PayloadModel):
    """Payload of an ``interrupt.answered`` event."""

    id: str
    external_id: str | None
    title: str
    answered: Literal[True]
    answered_at: AwareDatetime
    action_requests: list[AnsweredActionRequest]


class InterruptAnsweredEvent(_PayloadModel):
    """Every action request on an interrupt was decided."""

    type: Literal["interrupt.answered"]
    timestamp: AwareDatetime
    data: InterruptAnsweredData


class InterruptEscalatedData(_PayloadModel):
    """Payload of an ``interrupt.escalated`` event."""

    id: str
    external_id: str | None
    title: str
    escalated: Literal[True]


class InterruptEscalatedEvent(_PayloadModel):
    """An interrupt was raised to the manager review queue."""

    type: Literal["interrupt.escalated"]
    timestamp: AwareDatetime
    data: InterruptEscalatedData


class SessionEndReason(str, Enum):
    """Why a live session ended."""

    agent = "agent"
    """The agent ended the session itself (``Client.end_session``)."""
    timeout = "timeout"
    """The session went quiet past the organisation's session timeout and was closed automatically."""
    manual = "manual"
    """A watcher disconnected the session from Live View."""


class _SessionData(_PayloadModel):
    """Fields shared by every ``session.*`` payload."""

    id: str
    external_id: str | None
    name: str
    """The agent's self-declared name, e.g. ``"billing-agent"``."""


class SessionStartedData(_SessionData):
    """Payload of a ``session.started`` event."""

    started_at: AwareDatetime


class SessionStartedEvent(_PayloadModel):
    """An agent registered a live session."""

    type: Literal["session.started"]
    timestamp: AwareDatetime
    data: SessionStartedData


class SessionEndedData(_SessionData):
    """Payload of a ``session.ended`` event."""

    started_at: AwareDatetime
    ended_at: AwareDatetime
    reason: SessionEndReason


class SessionEndedEvent(_PayloadModel):
    """A live session ended - by the agent, a watcher, or the session timeout."""

    type: Literal["session.ended"]
    timestamp: AwareDatetime
    data: SessionEndedData


class SessionActionData(_SessionData):
    """Payload of a ``session.action`` event."""

    action: str
    """The custom action's name, as defined on the organisation's integrations page."""
    triggered_by: str
    """The member who fired the action from Live View."""


class SessionActionEvent(_PayloadModel):
    """A watcher fired a custom action against a live session."""

    type: Literal["session.action"]
    timestamp: AwareDatetime
    data: SessionActionData


class UnknownEvent(_PayloadModel):
    """A verified event whose type this SDK version does not know.

    Newer Vigilator event types fall through to this model instead of raising,
    so handlers written against an older SDK keep working. Upgrade the SDK to
    get a typed model.
    """

    type: str
    timestamp: AwareDatetime | None = None
    data: Any = None


WebhookEvent = Union[  # noqa: UP007 - Union keeps the alias usable in isinstance checks on 3.10
    InterruptCreatedEvent,
    InterruptAnsweredEvent,
    InterruptEscalatedEvent,
    SessionStartedEvent,
    SessionEndedEvent,
    SessionActionEvent,
    UnknownEvent,
]

_EVENT_MODELS: dict[str, type[WebhookEvent]] = {
    "interrupt.created": InterruptCreatedEvent,
    "interrupt.answered": InterruptAnsweredEvent,
    "interrupt.escalated": InterruptEscalatedEvent,
    "session.started": SessionStartedEvent,
    "session.ended": SessionEndedEvent,
    "session.action": SessionActionEvent,
}


class WebhookHandler:
    """Verifies Vigilator webhook deliveries and dispatches them to callbacks.

    The handler is framework-agnostic: feed it the raw request body and the
    request headers from any web framework. Always pass the raw body bytes as
    received - re-serializing parsed JSON breaks the signature.

    Example:
        >>> webhooks = WebhookHandler(secret="whsec_...")
        >>>
        >>> @webhooks.on("interrupt.answered")
        ... def resume_agent(event: InterruptAnsweredEvent) -> None:
        ...     ...
        >>>
        >>> # inside the route: webhooks.handle(raw_body, request_headers)

    Attributes:
        tolerance: Maximum allowed clock skew for ``svix-timestamp``, in seconds.

    """

    def __init__(self, secret: str, tolerance: float = DEFAULT_TOLERANCE):
        """Initialize the handler with an endpoint signing secret.

        Args:
            secret: The endpoint's signing secret from the Vigilator dashboard,
                with or without the ``whsec_`` prefix.
            tolerance: Maximum allowed clock skew for ``svix-timestamp``, in
                seconds. Deliveries outside the window are rejected to prevent
                replay attacks.

        Raises:
            WebhookVerificationError: The secret is not valid base64.

        """
        try:
            self._secret = base64.b64decode(secret.removeprefix(_WHSEC_PREFIX), validate=True)
        except ValueError:
            raise WebhookVerificationError(_ERR_BAD_WHSEC) from None
        if not self._secret:
            raise WebhookVerificationError(_ERR_BAD_WHSEC)
        self.tolerance = tolerance
        self._callbacks: dict[str, list[Callable[[Any], object]]] = {}

    def verify(self, body: bytes | str, headers: Mapping[str, str]) -> None:
        """Verify the Svix signature of a delivery, without parsing the body.

        Args:
            body: Raw request body, exactly as received.
            headers: Request headers; header names are matched case-insensitively.

        Raises:
            WebhookVerificationError: Headers are missing or malformed, the
                timestamp is outside the tolerance window, or no signature
                matches the body.

        """
        lowered = {key.lower(): value for key, value in headers.items()}
        message_id = lowered.get("svix-id")
        timestamp = lowered.get("svix-timestamp")
        signature_header = lowered.get("svix-signature")
        if not message_id or not timestamp or not signature_header:
            raise WebhookVerificationError(_ERR_MISSING_HEADERS)
        self._check_timestamp(timestamp)

        if isinstance(body, bytes):
            try:
                body = body.decode("utf-8")
            except UnicodeDecodeError:
                raise WebhookVerificationError(_ERR_BODY_NOT_UTF8) from None
        signed_content = f"{message_id}.{timestamp}.{body}".encode()
        expected = hmac.new(self._secret, signed_content, "sha256").digest()

        # The header holds space-delimited "<version>,<base64>" entries; any
        # matching v1 signature verifies the delivery.
        for candidate in signature_header.split(" "):
            version, _, signature = candidate.partition(",")
            if version != _SIGNATURE_VERSION:
                continue
            try:
                signature_bytes = base64.b64decode(signature, validate=True)
            except ValueError:
                continue
            if hmac.compare_digest(expected, signature_bytes):
                return
        raise WebhookVerificationError(_ERR_NO_MATCHING_SIGNATURE)

    def _check_timestamp(self, timestamp: str) -> None:
        """Reject timestamps outside the tolerance window, to prevent replays."""
        try:
            timestamp_value = float(timestamp)
        except ValueError:
            raise WebhookVerificationError(_ERR_BAD_TIMESTAMP) from None
        now = time.time()
        if timestamp_value < now - self.tolerance:
            raise WebhookVerificationError(_ERR_TIMESTAMP_TOO_OLD)
        if timestamp_value > now + self.tolerance:
            raise WebhookVerificationError(_ERR_TIMESTAMP_TOO_NEW)

    def construct_event(self, body: bytes | str, headers: Mapping[str, str]) -> WebhookEvent:
        """Verify a delivery and parse its body into a typed event.

        Args:
            body: Raw request body, exactly as received.
            headers: Request headers; header names are matched case-insensitively.

        Returns:
            The typed event; an UnknownEvent when the event type postdates this
            SDK version.

        Raises:
            WebhookVerificationError: The delivery failed verification or the
                body is not valid JSON.
            pydantic.ValidationError: The verified payload does not match the
                published payload contract.

        """
        self.verify(body, headers)
        try:
            payload = json.loads(body)
        except ValueError:
            raise WebhookVerificationError(_ERR_BODY_NOT_JSON) from None
        event_type = payload.get("type") if isinstance(payload, dict) else None
        model = _EVENT_MODELS.get(event_type, UnknownEvent)
        return model.model_validate(payload)

    def on(self, event_type: str) -> Callable[[Callable[[Any], object]], Callable[[Any], object]]:
        """Register a callback for one event type, as a decorator.

        Args:
            event_type: The event type to subscribe to, e.g. ``"interrupt.answered"``.
                Unknown types are allowed, so callbacks can target event types
                newer than this SDK version.

        Returns:
            The decorator; it registers the callback and returns it unchanged.

        """

        def decorator(callback: Callable[[Any], object]) -> Callable[[Any], object]:
            self._callbacks.setdefault(event_type, []).append(callback)
            return callback

        return decorator

    def handle(self, body: bytes | str, headers: Mapping[str, str]) -> WebhookEvent:
        """Verify a delivery, parse it, and invoke the callbacks registered for its type.

        Callbacks run synchronously in registration order; return a 2xx quickly
        after this call and offload slow work, as Svix retries failed deliveries.

        Args:
            body: Raw request body, exactly as received.
            headers: Request headers; header names are matched case-insensitively.

        Returns:
            The typed event, after all callbacks for it have run.

        Raises:
            WebhookVerificationError: The delivery failed verification or the
                body is not valid JSON.
            pydantic.ValidationError: The verified payload does not match the
                published payload contract.

        """
        event = self.construct_event(body, headers)
        for callback in self._callbacks.get(event.type, []):
            callback(event)
        return event

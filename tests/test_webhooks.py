"""Tests for webhook verification and dispatch."""

import base64
import hashlib
import hmac
import json
import time

import pytest
from pydantic import ValidationError

from vigilator_py_sdk import (
    Decision,
    InterruptAnsweredEvent,
    InterruptCreatedEvent,
    InterruptEscalatedEvent,
    UnknownEvent,
    WebhookHandler,
    WebhookVerificationError,
)

SECRET_BYTES = b"test-signing-secret-32-bytes-ok!"
SECRET = "whsec_" + base64.b64encode(SECRET_BYTES).decode()

# The example payloads from the app's event catalogue (lib/webhook-events.ts).
CREATED_PAYLOAD = {
    "type": "interrupt.created",
    "timestamp": "2025-09-10T08:03:12Z",
    "data": {
        "id": "8f14e45f-ceea-4672-8657-a1b2c3d4e5f6",
        "externalId": "run_42",
        "title": "Send onboarding email",
        "description": "The agent wants to email a new customer.",
        "classification": "billing",
        "actionRequests": [
            {
                "name": "send_email",
                "args": {"to": "customer@example.com"},
                "allowedDecisions": ["approve", "edit", "reject"],
            }
        ],
    },
}

ANSWERED_PAYLOAD = {
    "type": "interrupt.answered",
    "timestamp": "2025-09-10T08:11:47Z",
    "data": {
        "id": "8f14e45f-ceea-4672-8657-a1b2c3d4e5f6",
        "externalId": "run_42",
        "title": "Send onboarding email",
        "answered": True,
        "answeredAt": "2025-09-10T08:11:47Z",
        "actionRequests": [
            {
                "name": "send_email",
                "decision": "approve",
                "decidedByName": "Ada Lovelace",
                "editedArgs": None,
                "responseText": None,
            }
        ],
    },
}

ESCALATED_PAYLOAD = {
    "type": "interrupt.escalated",
    "timestamp": "2025-09-10T09:20:05Z",
    "data": {
        "id": "8f14e45f-ceea-4672-8657-a1b2c3d4e5f6",
        "externalId": "run_42",
        "title": "Send onboarding email",
        "escalated": True,
    },
}


def sign(
    body: bytes,
    secret: bytes = SECRET_BYTES,
    message_id: str = "msg_1",
    timestamp: float | None = None,
) -> dict[str, str]:
    """Build the Svix signature headers for a body, the way Svix signs deliveries."""
    ts = str(int(time.time() if timestamp is None else timestamp))
    signed_content = f"{message_id}.{ts}.{body.decode()}".encode()
    signature = base64.b64encode(hmac.new(secret, signed_content, hashlib.sha256).digest()).decode()
    return {"svix-id": message_id, "svix-timestamp": ts, "svix-signature": f"v1,{signature}"}


def encode(payload: dict) -> bytes:
    """Serialize a payload the way the delivery body arrives on the wire."""
    return json.dumps(payload).encode()


def test_created_event_parsed():
    """A signed interrupt.created delivery parses into a typed event."""
    body = encode(CREATED_PAYLOAD)
    event = WebhookHandler(SECRET).construct_event(body, sign(body))

    assert isinstance(event, InterruptCreatedEvent)
    assert event.data.external_id == "run_42"
    assert event.data.classification == "billing"
    request = event.data.action_requests[0]
    assert request.args == {"to": "customer@example.com"}
    assert request.allowed_decisions == [Decision.approve, Decision.edit, Decision.reject]


def test_answered_event_parsed():
    """A signed interrupt.answered delivery parses into a typed event."""
    body = encode(ANSWERED_PAYLOAD)
    event = WebhookHandler(SECRET).construct_event(body, sign(body))

    assert isinstance(event, InterruptAnsweredEvent)
    assert event.data.answered is True
    request = event.data.action_requests[0]
    assert request.decision is Decision.approve
    assert request.decided_by_name == "Ada Lovelace"
    assert request.edited_args is None


def test_escalated_event_parsed():
    """A signed interrupt.escalated delivery parses into a typed event."""
    body = encode(ESCALATED_PAYLOAD)
    event = WebhookHandler(SECRET).construct_event(body, sign(body))

    assert isinstance(event, InterruptEscalatedEvent)
    assert event.data.escalated is True


def test_secret_prefix_optional():
    """The signing secret is accepted with or without the whsec_ prefix."""
    body = encode(ESCALATED_PAYLOAD)
    handler = WebhookHandler(base64.b64encode(SECRET_BYTES).decode())
    assert isinstance(handler.construct_event(body, sign(body)), InterruptEscalatedEvent)


def test_invalid_secret():
    """A secret that is not valid base64 is rejected at construction."""
    with pytest.raises(WebhookVerificationError):
        WebhookHandler("whsec_not!base64")


def test_tampered_body():
    """A body that differs from the signed one fails verification."""
    headers = sign(encode(CREATED_PAYLOAD))
    tampered = encode({**CREATED_PAYLOAD, "type": "interrupt.escalated"})
    with pytest.raises(WebhookVerificationError):
        WebhookHandler(SECRET).construct_event(tampered, headers)


def test_wrong_secret():
    """A delivery signed with a different secret fails verification."""
    body = encode(CREATED_PAYLOAD)
    headers = sign(body, secret=b"some-other-signing-secret-bytes!")
    with pytest.raises(WebhookVerificationError):
        WebhookHandler(SECRET).construct_event(body, headers)


def test_missing_headers():
    """A delivery without the Svix headers fails verification."""
    body = encode(CREATED_PAYLOAD)
    with pytest.raises(WebhookVerificationError):
        WebhookHandler(SECRET).construct_event(body, {})


def test_stale_timestamp():
    """A timestamp older than the tolerance is rejected as a possible replay."""
    body = encode(CREATED_PAYLOAD)
    headers = sign(body, timestamp=time.time() - 600)
    with pytest.raises(WebhookVerificationError):
        WebhookHandler(SECRET).construct_event(body, headers)


def test_future_timestamp():
    """A timestamp further in the future than the tolerance is rejected."""
    body = encode(CREATED_PAYLOAD)
    headers = sign(body, timestamp=time.time() + 600)
    with pytest.raises(WebhookVerificationError):
        WebhookHandler(SECRET).construct_event(body, headers)


def test_malformed_timestamp():
    """A svix-timestamp header that is not a number is rejected."""
    body = encode(CREATED_PAYLOAD)
    headers = {**sign(body), "svix-timestamp": "yesterday"}
    with pytest.raises(WebhookVerificationError):
        WebhookHandler(SECRET).construct_event(body, headers)


def test_multiple_signatures():
    """Any matching v1 signature among several verifies the delivery."""
    body = encode(CREATED_PAYLOAD)
    headers = sign(body)
    good = headers["svix-signature"]
    bogus = base64.b64encode(b"0" * 32).decode()
    headers["svix-signature"] = f"v1a,{bogus} v1,not-base64 v1,{bogus} {good}"
    assert isinstance(WebhookHandler(SECRET).construct_event(body, headers), InterruptCreatedEvent)


def test_case_insensitive_headers():
    """Header names are matched case-insensitively, whatever the framework passes."""
    body = encode(CREATED_PAYLOAD)
    headers = {key.title(): value for key, value in sign(body).items()}
    assert isinstance(WebhookHandler(SECRET).construct_event(body, headers), InterruptCreatedEvent)


def test_unknown_event_type():
    """An event type newer than this SDK falls through to UnknownEvent."""
    payload = {"type": "interrupt.reopened", "timestamp": "2025-09-10T10:00:00Z", "data": {"id": "int_1"}}
    body = encode(payload)
    event = WebhookHandler(SECRET).construct_event(body, sign(body))

    assert isinstance(event, UnknownEvent)
    assert event.type == "interrupt.reopened"
    assert event.data == {"id": "int_1"}


def test_non_json_body():
    """A verified body that is not JSON raises WebhookVerificationError."""
    body = b"not json"
    with pytest.raises(WebhookVerificationError):
        WebhookHandler(SECRET).construct_event(body, sign(body))


def test_contract_mismatch():
    """A known event type whose payload breaks the contract raises ValidationError."""
    payload = {"type": "interrupt.created", "timestamp": "2025-09-10T08:03:12Z", "data": {"id": "int_1"}}
    body = encode(payload)
    with pytest.raises(ValidationError):
        WebhookHandler(SECRET).construct_event(body, sign(body))


def test_handle_dispatches_to_registered_callbacks():
    """handle() invokes the callbacks registered for the event's type, and only those."""
    webhooks = WebhookHandler(SECRET)
    received = []

    @webhooks.on("interrupt.answered")
    def on_answered(event: InterruptAnsweredEvent) -> None:
        received.append(event)

    @webhooks.on("interrupt.created")
    def on_created(event: InterruptCreatedEvent) -> None:
        raise AssertionError("callback for another event type must not run")

    body = encode(ANSWERED_PAYLOAD)
    event = webhooks.handle(body, sign(body))

    assert received == [event]
    assert isinstance(event, InterruptAnsweredEvent)


def test_handle_without_callbacks():
    """handle() still verifies and returns the event when nothing is registered."""
    body = encode(ESCALATED_PAYLOAD)
    event = WebhookHandler(SECRET).handle(body, sign(body))
    assert isinstance(event, InterruptEscalatedEvent)

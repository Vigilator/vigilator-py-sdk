"""Tests for the Vigilator API client."""

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import ValidationError

from vigilator_py_sdk import (
    ActionRequest,
    AllowedDecision,
    APIError,
    Client,
    InterruptsPostRequest,
    Message,
    MessageType,
    NotFoundError,
    SessionStatus,
    UsageLimitError,
    VigilatorConnectionError,
    WorkspaceLimitError,
)

INTERRUPT = InterruptsPostRequest(
    title="Refund request",
    description="Agent wants to refund an order.",
    actionRequests=[
        ActionRequest(name="refund_order", allowedDecisions=[AllowedDecision.approve, AllowedDecision.reject])
    ],
)

SUCCESS_BODY = {
    "id": "int_1",
    "timeOpened": "2026-08-06T14:00:00Z",
    "createdAt": "2026-08-06T14:00:00Z",
    "updatedAt": "2026-08-06T14:00:00Z",
    "organizationId": "org_1",
    "externalId": None,
    "title": "Refund request",
    "answered": False,
    "answeredAt": None,
    "description": "Agent wants to refund an order.",
    "escalated": False,
    "assigneeId": None,
    "assignee": None,
    "classificationId": None,
    "classification": None,
    "argusSummary": None,
    "argusSuggestedDecision": None,
    "argusSuggestedResponse": None,
    "messages": [],
    "actionRequests": [],
    "auditEvents": [],
}


PROMPT = Message(type=MessageType.human, content="Refund order #42")

SESSION_BODY = {
    "id": "ses_1",
    "createdAt": "2026-08-06T14:00:00Z",
    "updatedAt": "2026-08-06T14:00:00Z",
    "organizationId": "org_1",
    "name": "billing-agent",
    "externalId": "thread_42",
    "status": "active",
    "startedAt": "2026-08-06T14:00:00Z",
    "endedAt": None,
    "escalated": False,
    "assigneeId": None,
    "assignee": None,
    "lastActivityAt": "2026-08-06T14:00:00Z",
    "messages": [
        {
            "id": "msg_1",
            "createdAt": "2026-08-06T14:00:00Z",
            "interruptId": None,
            "sessionId": "ses_1",
            "type": "human",
            "content": "Refund order #42",
            "name": None,
        }
    ],
    "messageCount": 1,
}


def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> Client:
    """Build a client whose requests are answered by the given handler."""
    return Client(key="test-key", transport=httpx.MockTransport(handler), retries=0)


def test_create_interrupt_success():
    """A 2xx response is validated into an InterruptsPostResponse."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=SUCCESS_BODY)

    with make_client(handler) as client:
        result = client.create_interrupt(INTERRUPT)

    assert result.id == "int_1"
    assert result.answered is False

    request = captured["request"]
    assert request.url.path == "/api/interrupts"
    assert request.headers["x-api-key"] == "test-key"
    assert request.headers["content-type"] == "application/json"
    # Unset optional fields are omitted, not sent as nulls.
    assert json.loads(request.content) == {
        "title": "Refund request",
        "description": "Agent wants to refund an order.",
        "actionRequests": [{"name": "refund_order", "allowedDecisions": ["approve", "reject"]}],
    }


def test_create_interrupt_usage_limit():
    """A 402 USAGE_LIMIT_REACHED response raises UsageLimitError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            402,
            json={
                "defined": True,
                "code": "USAGE_LIMIT_REACHED",
                "status": 402,
                "message": "Usage limit reached",
                "data": {"featureId": "interrupts", "message": "Upgrade your plan."},
            },
        )

    with make_client(handler) as client, pytest.raises(UsageLimitError) as exc_info:
        client.create_interrupt(INTERRUPT)

    assert exc_info.value.status == 402
    assert exc_info.value.code == "USAGE_LIMIT_REACHED"
    assert exc_info.value.data == {"featureId": "interrupts", "message": "Upgrade your plan."}


def test_create_interrupt_workspace_limit():
    """A 403 WORKSPACE_LIMIT_REACHED response raises WorkspaceLimitError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "defined": True,
                "code": "WORKSPACE_LIMIT_REACHED",
                "status": 403,
                "message": "Workspace limit reached",
                "data": {"message": "Workspace limit reached"},
            },
        )

    with make_client(handler) as client, pytest.raises(WorkspaceLimitError):
        client.create_interrupt(INTERRUPT)


def test_create_interrupt_unknown_error_body():
    """A non-JSON error response still raises an APIError with the status code."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    with make_client(handler) as client, pytest.raises(APIError) as exc_info:
        client.create_interrupt(INTERRUPT)

    assert exc_info.value.status == 500
    assert exc_info.value.code == "UNKNOWN"


def test_get_interrupt_success():
    """A 2xx response is validated into an InterruptsIdGetResponse."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=SUCCESS_BODY)

    with make_client(handler) as client:
        result = client.get_interrupt("int_1")

    assert result.id == "int_1"
    request = captured["request"]
    assert request.method == "GET"
    assert request.url.path == "/api/interrupts/int_1"
    assert request.headers["x-api-key"] == "test-key"


def test_get_interrupt_quotes_id():
    """The interrupt id is percent-encoded so it cannot alter the request path."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=SUCCESS_BODY)

    with make_client(handler) as client:
        client.get_interrupt("a/b")

    assert captured["request"].url.raw_path.endswith(b"/api/interrupts/a%2Fb")


def test_get_interrupt_not_found():
    """A 404 NOT_FOUND response raises NotFoundError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "defined": False,
                "code": "NOT_FOUND",
                "status": 404,
                "message": "Interrupt not found.",
            },
        )

    with make_client(handler) as client, pytest.raises(NotFoundError) as exc_info:
        client.get_interrupt("missing")

    assert exc_info.value.status == 404
    assert exc_info.value.code == "NOT_FOUND"


def test_create_interrupt_connection_error():
    """A network failure raises VigilatorConnectionError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with make_client(handler) as client, pytest.raises(VigilatorConnectionError):
        client.create_interrupt(INTERRUPT)


def test_start_session_success():
    """A 2xx response is validated into a SessionsPostResponse."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=SESSION_BODY)

    with make_client(handler) as client:
        session = client.start_session("billing-agent", external_id="thread_42", messages=[PROMPT])

    assert session.id == "ses_1"
    assert session.status is SessionStatus.active
    assert session.messageCount == 1
    assert session.messages[0].content == "Refund order #42"

    request = captured["request"]
    assert request.method == "POST"
    assert request.url.path == "/api/sessions"
    assert request.headers["x-api-key"] == "test-key"
    # Keyword arguments map onto the API's camelCase body; unset optional
    # fields are omitted, not sent as nulls.
    assert json.loads(request.content) == {
        "name": "billing-agent",
        "externalId": "thread_42",
        "messages": [{"type": "human", "content": "Refund order #42"}],
    }


def test_start_session_minimal_body():
    """Only the name is sent when no opening context is given."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=SESSION_BODY)

    with make_client(handler) as client:
        client.start_session("billing-agent")

    assert json.loads(captured["request"].content) == {"name": "billing-agent"}


def test_start_session_validates_before_sending():
    """Input that breaks the API contract is rejected client-side, without a request."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request must be sent")

    with make_client(handler) as client, pytest.raises(ValidationError):
        client.start_session("")


def test_start_session_usage_limit():
    """A 402 USAGE_LIMIT_REACHED response (agent hours exhausted) raises UsageLimitError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            402,
            json={
                "defined": True,
                "code": "USAGE_LIMIT_REACHED",
                "status": 402,
                "message": "Usage limit reached",
                "data": {"featureId": "agent_hours_monitored", "message": "Upgrade to Pro."},
            },
        )

    with make_client(handler) as client, pytest.raises(UsageLimitError) as exc_info:
        client.start_session("billing-agent")

    assert exc_info.value.data == {"featureId": "agent_hours_monitored", "message": "Upgrade to Pro."}


def test_append_session_messages_success():
    """Messages are posted to the session's messages endpoint and the session returned."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={**SESSION_BODY, "messageCount": 2})

    reply = Message(type=MessageType.ai, content="Refunding now.", name="billing-agent")
    with make_client(handler) as client:
        session = client.append_session_messages("ses_1", [reply])

    assert session.messageCount == 2
    request = captured["request"]
    assert request.method == "POST"
    assert request.url.path == "/api/sessions/ses_1/messages"
    assert json.loads(request.content) == {
        "messages": [{"type": "ai", "content": "Refunding now.", "name": "billing-agent"}],
    }


def test_append_session_messages_requires_messages():
    """An empty batch is rejected client-side, without a request."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request must be sent")

    with make_client(handler) as client, pytest.raises(ValidationError):
        client.append_session_messages("ses_1", [])


def test_append_session_messages_ended_session():
    """Appending to an ended session is a 409 CONFLICT, raised as a plain APIError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={"defined": False, "code": "CONFLICT", "status": 409, "message": "Session has already ended."},
        )

    with make_client(handler) as client, pytest.raises(APIError) as exc_info:
        client.append_session_messages("ses_1", [PROMPT])

    assert exc_info.value.status == 409
    assert exc_info.value.code == "CONFLICT"
    assert exc_info.value.message == "Session has already ended."


def test_end_session_success():
    """Ending a session posts to the end endpoint with no body."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={**SESSION_BODY, "status": "ended", "endedAt": "2026-08-06T14:30:00Z"})

    with make_client(handler) as client:
        session = client.end_session("ses_1")

    assert session.status is SessionStatus.ended
    assert session.endedAt is not None
    request = captured["request"]
    assert request.method == "POST"
    assert request.url.path == "/api/sessions/ses_1/end"
    assert request.content == b""


def test_end_session_quotes_id():
    """The session id is percent-encoded so it cannot alter the request path."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=SESSION_BODY)

    with make_client(handler) as client:
        client.end_session("a/b")

    assert captured["request"].url.raw_path.endswith(b"/api/sessions/a%2Fb/end")


def test_end_session_not_found():
    """A 404 NOT_FOUND response raises NotFoundError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"defined": False, "code": "NOT_FOUND", "status": 404, "message": "Session not found."},
        )

    with make_client(handler) as client, pytest.raises(NotFoundError):
        client.end_session("missing")

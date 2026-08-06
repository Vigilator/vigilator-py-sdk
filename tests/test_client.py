"""Tests for the Vigilator API client."""

import json
from collections.abc import Callable

import httpx
import pytest

from vigilator_py_sdk import (
    APIError,
    Client,
    InterruptsPostRequest,
    UsageLimitError,
    VigilatorConnectionError,
    WorkspaceLimitError,
)

INTERRUPT = InterruptsPostRequest(title="Refund request", description="Agent wants to refund an order.")

SUCCESS_BODY = {
    "id": "int_1",
    "timeOpened": "2026-08-06T14:00:00Z",
    "createdAt": "2026-08-06T14:00:00Z",
    "updatedAt": "2026-08-06T14:00:00Z",
    "organizationId": "org_1",
    "externalId": None,
    "title": "Refund request",
    "answered": False,
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
    assert request.url.path == "/interrupts"
    assert request.headers["x-api-key"] == "test-key"
    assert request.headers["content-type"] == "application/json"
    # Unset optional fields are omitted, not sent as nulls.
    assert json.loads(request.content) == {
        "title": "Refund request",
        "description": "Agent wants to refund an order.",
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


def test_create_interrupt_connection_error():
    """A network failure raises VigilatorConnectionError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with make_client(handler) as client, pytest.raises(VigilatorConnectionError):
        client.create_interrupt(INTERRUPT)

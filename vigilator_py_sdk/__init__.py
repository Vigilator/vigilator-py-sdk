"""Vigilator Python SDK."""

from vigilator_py_sdk.exceptions import (
    AddonRequiredError,
    APIError,
    NotFoundError,
    PlanRequiredError,
    UsageLimitError,
    VigilatorConnectionError,
    VigilatorError,
    WebhookVerificationError,
    WorkspaceLimitError,
)
from vigilator_py_sdk.main import Client
from vigilator_py_sdk.models import (
    ActionRequest,
    AllowedDecision,
    InterruptsIdGetResponse,
    InterruptsPostRequest,
    InterruptsPostResponse,
    Message,
    SessionsIdEndPostResponse,
    SessionsIdMessagesPostResponse,
    SessionsPostResponse,
)

# The generated enum names are too generic to export as-is.
from vigilator_py_sdk.models import Status as SessionStatus
from vigilator_py_sdk.models import Type as MessageType
from vigilator_py_sdk.webhooks import (
    Decision,
    InterruptAnsweredEvent,
    InterruptCreatedEvent,
    InterruptEscalatedEvent,
    SessionActionEvent,
    SessionEndedEvent,
    SessionEndReason,
    SessionStartedEvent,
    UnknownEvent,
    WebhookEvent,
    WebhookHandler,
)

__all__ = [
    "APIError",
    "ActionRequest",
    "AddonRequiredError",
    "AllowedDecision",
    "Client",
    "Decision",
    "InterruptAnsweredEvent",
    "InterruptCreatedEvent",
    "InterruptEscalatedEvent",
    "InterruptsIdGetResponse",
    "InterruptsPostRequest",
    "InterruptsPostResponse",
    "Message",
    "MessageType",
    "NotFoundError",
    "PlanRequiredError",
    "SessionActionEvent",
    "SessionEndReason",
    "SessionEndedEvent",
    "SessionStartedEvent",
    "SessionStatus",
    "SessionsIdEndPostResponse",
    "SessionsIdMessagesPostResponse",
    "SessionsPostResponse",
    "UnknownEvent",
    "UsageLimitError",
    "VigilatorConnectionError",
    "VigilatorError",
    "WebhookEvent",
    "WebhookHandler",
    "WebhookVerificationError",
    "WorkspaceLimitError",
]

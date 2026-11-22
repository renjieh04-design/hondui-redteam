"""Provider-independent inputs and outputs for target-model execution."""

from typing import Self

from pydantic import Field, PositiveInt, model_validator

from redteam.core.models.common import DomainModel, NonEmptyStr
from redteam.core.models.execution import HttpStatusCode
from redteam.core.models.interaction import (
    ConversationMessage,
    MessageRole,
    validate_conversation,
)
from redteam.core.models.task import TargetConfig


class TargetExecutionRequest(DomainModel):
    """One logical, provider-independent target execution requested by TaskRunner."""

    task_id: NonEmptyStr
    test_item_id: NonEmptyStr
    case_id: NonEmptyStr
    step_id: NonEmptyStr
    round_index: PositiveInt
    call_id: NonEmptyStr
    target: TargetConfig
    messages: tuple[ConversationMessage, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_target_conversation(self) -> Self:
        validate_conversation(self.messages, final_role=MessageRole.USER)
        return self


class TargetAdapterRequest(DomainModel):
    """The connection and conversation supplied for one physical target call."""

    target: TargetConfig
    messages: tuple[ConversationMessage, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_target_conversation(self) -> Self:
        validate_conversation(self.messages, final_role=MessageRole.USER)
        return self


class TargetAdapterResponse(DomainModel):
    """A successful target response normalized by a target adapter."""

    response_text: NonEmptyStr
    http_status_code: HttpStatusCode | None = None
    provider_request_id: NonEmptyStr | None = None

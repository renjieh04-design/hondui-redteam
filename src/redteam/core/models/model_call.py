"""Provider-independent model-client request and response models."""

from typing import Self

from pydantic import Field, NonNegativeInt, PositiveInt, model_validator

from redteam.core.models.common import DomainModel, NonEmptyStr
from redteam.core.models.interaction import (
    ConversationMessage,
    MessageRole,
    validate_conversation,
)


class ModelRequest(DomainModel):
    """One normalized request sent through an attacker or judge ModelClient."""

    messages: tuple[ConversationMessage, ...] = Field(min_length=1)
    max_output_tokens: PositiveInt | None = None

    @model_validator(mode="after")
    def validate_model_conversation(self) -> Self:
        validate_conversation(self.messages, final_role=MessageRole.USER)
        return self


class ModelTokenUsage(DomainModel):
    """Provider-reported token counts when they are available."""

    input_tokens: NonNegativeInt
    output_tokens: NonNegativeInt


class ModelResponse(DomainModel):
    """A successful provider response normalized by ModelClient."""

    text: NonEmptyStr
    provider_request_id: NonEmptyStr | None = None
    usage: ModelTokenUsage | None = None

"""Provider-independent conversation messages shared by public interfaces."""

from enum import StrEnum

from redteam.core.models.common import DomainModel, NonEmptyStr


class MessageRole(StrEnum):
    """A role in a provider-independent model conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ConversationMessage(DomainModel):
    """One normalized message without provider-specific request fields."""

    role: MessageRole
    content: NonEmptyStr


def validate_conversation(
    messages: tuple[ConversationMessage, ...],
    *,
    final_role: MessageRole,
) -> None:
    """Require an optional system message followed by alternating turns."""

    if not messages:
        raise ValueError("conversation must contain at least one message")

    start_index = 1 if messages[0].role is MessageRole.SYSTEM else 0
    dialogue = messages[start_index:]
    if not dialogue:
        raise ValueError("conversation must contain at least one user message")
    if any(message.role is MessageRole.SYSTEM for message in dialogue):
        raise ValueError("a system message is only allowed at the beginning")

    expected_role = MessageRole.USER
    for message in dialogue:
        if message.role is not expected_role:
            raise ValueError("conversation roles must alternate from user to assistant")
        expected_role = (
            MessageRole.ASSISTANT
            if expected_role is MessageRole.USER
            else MessageRole.USER
        )

    if messages[-1].role is not final_role:
        raise ValueError(f"conversation must end with a {final_role.value} message")

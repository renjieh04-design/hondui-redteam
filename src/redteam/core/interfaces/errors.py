"""Typed failures that form part of the public module interfaces."""

from redteam.core.models.evaluation import EvaluationErrorType
from redteam.core.models.execution import ExecutionErrorType, HttpStatusCode
from redteam.core.models.retry import RetryableErrorType


class InterfaceError(Exception):
    """Base class for sanitized failures crossing a public interface."""


class ConfigurationLoadError(InterfaceError):
    """A task configuration could not be read or validated."""


class ResourceResolutionError(InterfaceError):
    """A referenced dataset, risk, strategy, or rule could not be resolved."""


class PersistenceError(InterfaceError):
    """A typed run record could not be saved or loaded."""


class ReportExportError(InterfaceError):
    """A requested report artifact could not be produced."""


class RetryableInterfaceError(InterfaceError):
    """A sanitized failure with an optional TaskRunner retry classification."""

    def __init__(
        self,
        message: str,
        *,
        retryable_error_type: RetryableErrorType | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable_error_type = retryable_error_type


class AttackerError(RetryableInterfaceError):
    """Attacker decision or generated-case production failed."""


class ModelClientError(RetryableInterfaceError):
    """A provider-independent attacker or judge model call failed."""


class EvidenceStoreError(RetryableInterfaceError):
    """Evidence content could not be written or read."""


class TargetAdapterError(RetryableInterfaceError):
    """One physical target call failed before it could be normalized."""

    def __init__(
        self,
        message: str,
        *,
        error_type: ExecutionErrorType,
        retryable_error_type: RetryableErrorType | None = None,
        http_status_code: HttpStatusCode | None = None,
        partial_response_text: str | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            retryable_error_type=retryable_error_type,
        )
        self.error_type = error_type
        self.http_status_code = http_status_code
        self.partial_response_text = partial_response_text
        self.provider_request_id = provider_request_id


class ScorerError(RetryableInterfaceError):
    """One scorer failed before it could produce a ScorerResult."""

    def __init__(
        self,
        message: str,
        *,
        error_type: EvaluationErrorType,
        retryable_error_type: RetryableErrorType | None = None,
    ) -> None:
        super().__init__(
            message,
            retryable_error_type=retryable_error_type,
        )
        self.error_type = error_type

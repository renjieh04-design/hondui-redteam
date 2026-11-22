"""Public run-record and evidence persistence interfaces."""

from typing import Protocol, runtime_checkable

from redteam.core.models.case import TestCase
from redteam.core.models.context import TaskContext
from redteam.core.models.decision import AttackDecision
from redteam.core.models.evaluation import EvaluationResult
from redteam.core.models.evidence import EvidenceReference, EvidenceWriteRequest
from redteam.core.models.execution import ExecutionResult
from redteam.core.models.run_records import TaskRunRecords
from redteam.core.models.step import StepContext
from redteam.core.models.task import TaskDefinition


@runtime_checkable
class RunRepository(Protocol):
    """Persist and reconstruct typed records without exposing SQLite details."""

    def save_task_definition(self, value: TaskDefinition) -> None: ...

    def save_task_context(self, value: TaskContext) -> None: ...

    def save_test_case(self, value: TestCase) -> None: ...

    def save_step_context(self, value: StepContext) -> None: ...

    def save_attack_decision(self, value: AttackDecision) -> None: ...

    def save_execution_result(self, value: ExecutionResult) -> None: ...

    def save_evaluation_result(self, value: EvaluationResult) -> None: ...

    def save_evidence_reference(self, value: EvidenceReference) -> None: ...

    def load_task_run(self, task_id: str) -> TaskRunRecords:
        """Return one complete typed run or raise PersistenceError."""

        ...


@runtime_checkable
class EvidenceStore(Protocol):
    """Persist redacted evidence content and return immutable references."""

    def write(self, request: EvidenceWriteRequest) -> EvidenceReference:
        """Atomically store content and metadata or raise EvidenceStoreError."""

        ...

    def read(self, reference: EvidenceReference) -> bytes:
        """Return exact stored bytes after integrity verification."""

        ...

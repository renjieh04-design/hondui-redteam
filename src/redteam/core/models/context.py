"""TaskRunner 维护的任务级运行上下文模型。"""

from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, Field, NonNegativeInt, model_validator

from redteam.core.models.task import DomainModel, NonEmptyStr


class TaskStatus(StrEnum):
    """整个任务的运行状态。"""

    CREATED = "created"
    PREPARING = "preparing"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class TestItemStatus(StrEnum):
    """单个测试项的运行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class TerminationReason(StrEnum):
    """任务进入最终状态的任务级原因。"""

    ALL_TEST_ITEMS_COMPLETED = "all_test_items_completed"
    RESOURCE_PREPARATION_FAILED = "resource_preparation_failed"
    TARGET_UNAVAILABLE = "target_unavailable"
    INTERNAL_ERROR = "internal_error"
    USER_CANCELLED = "user_cancelled"


class TestItemProgress(DomainModel):
    """一个 TestItem 的执行进度汇总，不包含具体用例结果。"""

    test_item_id: NonEmptyStr
    status: TestItemStatus = TestItemStatus.PENDING
    total_cases: NonNegativeInt | None = None
    completed_cases: NonNegativeInt = 0
    error_cases: NonNegativeInt = 0

    @model_validator(mode="after")
    def validate_counts_and_status(self) -> Self:
        if self.total_cases is not None and self.completed_cases > self.total_cases:
            raise ValueError("completed_cases cannot exceed total_cases")
        if self.error_cases > self.completed_cases:
            raise ValueError("error_cases cannot exceed completed_cases")

        if self.status is TestItemStatus.PENDING and self.completed_cases:
            raise ValueError("a pending test item cannot contain completed cases")

        if self.status in {
            TestItemStatus.COMPLETED,
            TestItemStatus.COMPLETED_WITH_ERRORS,
        }:
            if self.total_cases is None:
                raise ValueError("a completed test item must have total_cases")
            if self.completed_cases != self.total_cases:
                raise ValueError(
                    "a completed test item must have completed all of its cases"
                )

        if self.status is TestItemStatus.COMPLETED and self.error_cases != 0:
            raise ValueError("a completed test item cannot contain case errors")
        if (
            self.status is TestItemStatus.COMPLETED_WITH_ERRORS
            and self.error_cases == 0
        ):
            raise ValueError("completed_with_errors requires at least one case error")

        return self


class TaskContext(DomainModel):
    """TaskRunner 对一次完整任务运行维护的任务级状态快照。

    current_* 字段只是指向当前对象的 ID，不嵌入 TestCase、StepContext、
    AttackDecision 或任何执行与评估结果。
    """

    task_id: NonEmptyStr
    status: TaskStatus = TaskStatus.CREATED

    current_test_item_id: NonEmptyStr | None = None
    current_case_id: NonEmptyStr | None = None
    current_step_id: NonEmptyStr | None = None

    test_item_progress: tuple[TestItemProgress, ...] = Field(min_length=1)

    created_at: AwareDatetime
    started_at: AwareDatetime | None = None
    updated_at: AwareDatetime
    finished_at: AwareDatetime | None = None

    termination_reason: TerminationReason | None = None
    termination_detail: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_context_relationships(self) -> Self:
        progress_ids = [progress.test_item_id for progress in self.test_item_progress]
        if len(progress_ids) != len(set(progress_ids)):
            raise ValueError("test item progress IDs must be unique within a task")

        if (
            self.current_test_item_id is not None
            and self.current_test_item_id not in progress_ids
        ):
            raise ValueError(
                "current_test_item_id must refer to an item in test_item_progress"
            )
        if self.current_case_id is not None and self.current_test_item_id is None:
            raise ValueError("current_case_id requires current_test_item_id")
        if self.current_step_id is not None and self.current_case_id is None:
            raise ValueError("current_step_id requires current_case_id")

        final_statuses = {
            TaskStatus.COMPLETED,
            TaskStatus.COMPLETED_WITH_ERRORS,
            TaskStatus.FAILED,
        }
        is_final = self.status in final_statuses
        if is_final and self.finished_at is None:
            raise ValueError("a task in a final status must have finished_at")
        if is_final and self.termination_reason is None:
            raise ValueError("a task in a final status must have termination_reason")
        if not is_final and self.finished_at is not None:
            raise ValueError("a non-final task cannot have finished_at")
        if not is_final and self.termination_reason is not None:
            raise ValueError("a non-final task cannot have termination_reason")
        if self.termination_detail is not None and self.termination_reason is None:
            raise ValueError("termination_detail requires termination_reason")

        if self.status in {TaskStatus.COMPLETED, TaskStatus.COMPLETED_WITH_ERRORS}:
            if self.termination_reason is not TerminationReason.ALL_TEST_ITEMS_COMPLETED:
                raise ValueError("a completed task requires all_test_items_completed")
            item_statuses = {item.status for item in self.test_item_progress}
            if not item_statuses <= {
                TestItemStatus.COMPLETED,
                TestItemStatus.COMPLETED_WITH_ERRORS,
            }:
                raise ValueError("a completed task requires every test item to be completed")
            has_errors = TestItemStatus.COMPLETED_WITH_ERRORS in item_statuses
            if has_errors != (self.status is TaskStatus.COMPLETED_WITH_ERRORS):
                raise ValueError("task completion status must match test item errors")

        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        if self.started_at is not None:
            if self.started_at < self.created_at:
                raise ValueError("started_at cannot be earlier than created_at")
            if self.started_at > self.updated_at:
                raise ValueError("started_at cannot be later than updated_at")
        if self.finished_at is not None:
            earliest_finish = self.started_at or self.created_at
            if self.finished_at < earliest_finish:
                raise ValueError(
                    "finished_at cannot be earlier than the task start time"
                )
            if self.finished_at > self.updated_at:
                raise ValueError("finished_at cannot be later than updated_at")

        return self


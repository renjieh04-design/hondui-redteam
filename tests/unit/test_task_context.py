"""TaskContext 与 TestItemProgress 的领域约束测试。"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from redteam.core.models import (
    TaskContext,
    TaskStatus,
    TerminationReason,
    TestItemProgress as ItemProgress,
    TestItemStatus as ItemStatus,
)


NOW = datetime(2026, 11, 21, 10, 0, tzinfo=UTC)


def test_running_context_tracks_current_position_and_item_progress() -> None:
    context = TaskContext(
        task_id="run-001",
        status=TaskStatus.RUNNING,
        current_test_item_id="privacy-test",
        current_case_id="privacy-case-013",
        current_step_id="step-002",
        test_item_progress=(
            ItemProgress(
                test_item_id="baseline-test",
                status=ItemStatus.COMPLETED_WITH_ERRORS,
                total_cases=100,
                completed_cases=100,
                error_cases=2,
            ),
            ItemProgress(
                test_item_id="privacy-test",
                status=ItemStatus.RUNNING,
                total_cases=30,
                completed_cases=12,
                error_cases=1,
            ),
            ItemProgress(
                test_item_id="injection-test",
                total_cases=20,
            ),
        ),
        created_at=NOW,
        started_at=NOW + timedelta(seconds=1),
        updated_at=NOW + timedelta(minutes=5),
    )

    assert context.current_case_id == "privacy-case-013"
    assert context.current_step_id == "step-002"
    assert context.test_item_progress[1].completed_cases == 12


def test_item_progress_rejects_inconsistent_counters() -> None:
    with pytest.raises(ValidationError, match="completed_cases cannot exceed"):
        ItemProgress(
            test_item_id="privacy-test",
            total_cases=10,
            completed_cases=11,
        )

    with pytest.raises(ValidationError, match="error_cases cannot exceed"):
        ItemProgress(
            test_item_id="privacy-test",
            total_cases=10,
            completed_cases=2,
            error_cases=3,
        )


def test_context_rejects_duplicate_progress_ids() -> None:
    with pytest.raises(ValidationError, match="progress IDs must be unique"):
        TaskContext(
            task_id="run-002",
            test_item_progress=(
                ItemProgress(test_item_id="duplicate", total_cases=2),
                ItemProgress(test_item_id="duplicate", total_cases=3),
            ),
            created_at=NOW,
            updated_at=NOW,
        )


def test_current_position_must_form_a_valid_reference_chain() -> None:
    with pytest.raises(ValidationError, match="requires current_test_item_id"):
        TaskContext(
            task_id="run-003",
            current_case_id="case-001",
            test_item_progress=(ItemProgress(test_item_id="item-001"),),
            created_at=NOW,
            updated_at=NOW,
        )

    with pytest.raises(ValidationError, match="requires current_case_id"):
        TaskContext(
            task_id="run-004",
            current_test_item_id="item-001",
            current_step_id="step-001",
            test_item_progress=(ItemProgress(test_item_id="item-001"),),
            created_at=NOW,
            updated_at=NOW,
        )


def test_final_context_requires_finish_time_and_termination_reason() -> None:
    progress = ItemProgress(
        test_item_id="baseline-test",
        status=ItemStatus.COMPLETED,
        total_cases=10,
        completed_cases=10,
    )

    with pytest.raises(ValidationError, match="must have finished_at"):
        TaskContext(
            task_id="run-005",
            status=TaskStatus.COMPLETED,
            test_item_progress=(progress,),
            created_at=NOW,
            started_at=NOW,
            updated_at=NOW + timedelta(minutes=1),
            termination_reason=TerminationReason.ALL_TEST_ITEMS_COMPLETED,
        )

    context = TaskContext(
        task_id="run-005",
        status=TaskStatus.COMPLETED,
        test_item_progress=(progress,),
        created_at=NOW,
        started_at=NOW,
        updated_at=NOW + timedelta(minutes=1),
        finished_at=NOW + timedelta(minutes=1),
        termination_reason=TerminationReason.ALL_TEST_ITEMS_COMPLETED,
    )

    assert context.status is TaskStatus.COMPLETED


@pytest.mark.parametrize("item_status,errors,reason", [
    (ItemStatus.PENDING, 0, TerminationReason.ALL_TEST_ITEMS_COMPLETED),
    (ItemStatus.COMPLETED_WITH_ERRORS, 1, TerminationReason.ALL_TEST_ITEMS_COMPLETED),
    (ItemStatus.COMPLETED, 0, TerminationReason.USER_CANCELLED),
])
def test_completed_task_rejects_inconsistent_progress(item_status, errors, reason):
    progress = ItemProgress(
        test_item_id="item", status=item_status, total_cases=1,
        completed_cases=int(item_status is not ItemStatus.PENDING),
        error_cases=errors,
    )
    with pytest.raises(ValidationError):
        TaskContext(
            task_id="task", status=TaskStatus.COMPLETED,
            test_item_progress=(progress,), created_at=NOW,
            updated_at=NOW, finished_at=NOW, termination_reason=reason,
        )


def test_context_requires_timezone_on_every_timestamp():
    with pytest.raises(ValidationError, match="timezone"):
        TaskContext(
            task_id="task", test_item_progress=(ItemProgress(test_item_id="item"),),
            created_at=NOW, updated_at=NOW.replace(tzinfo=None),
        )


def test_pending_test_item_rejects_processed_cases():
    with pytest.raises(ValidationError, match="pending"):
        ItemProgress(test_item_id="item", total_cases=2, completed_cases=1)

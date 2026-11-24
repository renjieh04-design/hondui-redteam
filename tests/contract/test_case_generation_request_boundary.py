"""Check that model request boundaries reject structured connection data."""

import pytest
from pydantic import ValidationError

from redteam.core.models import CaseGenerationRequest, ModelRequest


@pytest.mark.parametrize("field", ["endpoint", "api_key", "api_key_ref", "headers"])
def test_case_generation_target_profile_rejects_connection_fields(field: str) -> None:
    payload = {
        "task_id": "fixture-task",
        "test_item_id": "fixture-item",
        "count": 1,
        "target_profile": {
            "name": "Fixture app",
            "description": "A local formatting fixture.",
            field: "synthetic-value",
        },
        "risk_objective": {
            "risk_id": "fixture-format",
            "name": "Format check",
            "description": "Check fixture formatting.",
            "objective": "Preserve fixture punctuation.",
        },
        "available_strategies": [
            {
                "strategy_id": "fixture-format",
                "name": "Fixed fixture",
                "description": "One harmless test record.",
                "guidance": "Use the fixed example text.",
            },
        ],
    }

    with pytest.raises(ValidationError) as error:
        CaseGenerationRequest.model_validate(payload)

    assert [(item["loc"], item["type"]) for item in error.value.errors()] == [
        (("target_profile", field), "extra_forbidden")
    ]


@pytest.mark.parametrize("field", ["endpoint", "model", "api_key_ref", "headers"])
def test_model_request_rejects_connection_fields(field: str) -> None:
    payload = {
        "messages": [{"role": "user", "content": "Check fixture punctuation."}],
        field: "synthetic-value",
    }

    with pytest.raises(ValidationError) as error:
        ModelRequest.model_validate(payload)

    assert [(item["loc"], item["type"]) for item in error.value.errors()] == [
        ((field,), "extra_forbidden")
    ]

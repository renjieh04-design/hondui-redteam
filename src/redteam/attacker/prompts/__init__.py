"""Provider-independent prompt builders for attacker model calls."""

from redteam.attacker.prompts.attack_decision import (
    build_attack_decision_request,
)
from redteam.attacker.prompts.case_generation import (
    build_case_generation_request,
)

__all__ = [
    "build_attack_decision_request",
    "build_case_generation_request",
]

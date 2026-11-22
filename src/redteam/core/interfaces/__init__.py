"""Public V1 module interfaces and their typed failure contract."""

from redteam.core.interfaces.attacker import Attacker
from redteam.core.interfaces.configuration import TaskDefinitionLoader
from redteam.core.interfaces.errors import (
    AttackerError,
    ConfigurationLoadError,
    EvidenceStoreError,
    InterfaceError,
    ModelClientError,
    PersistenceError,
    ReportExportError,
    ResourceResolutionError,
    RetryableInterfaceError,
    ScorerError,
    TargetAdapterError,
)
from redteam.core.interfaces.evaluation import Evaluator, Scorer
from redteam.core.interfaces.model_client import ModelClient
from redteam.core.interfaces.persistence import EvidenceStore, RunRepository
from redteam.core.interfaces.reporting import ReportExporter
from redteam.core.interfaces.resources import (
    AttackStrategyProvider,
    CaseGenerator,
    DatasetProvider,
    EvaluationRuleResolver,
    TaskResourceResolver,
)
from redteam.core.interfaces.runner import TaskRunner
from redteam.core.interfaces.target import TargetAdapter, TargetExecutor

__all__ = [
    "AttackStrategyProvider",
    "Attacker",
    "AttackerError",
    "CaseGenerator",
    "ConfigurationLoadError",
    "DatasetProvider",
    "Evaluator",
    "EvaluationRuleResolver",
    "EvidenceStore",
    "EvidenceStoreError",
    "InterfaceError",
    "ModelClient",
    "ModelClientError",
    "PersistenceError",
    "ReportExporter",
    "ReportExportError",
    "ResourceResolutionError",
    "RetryableInterfaceError",
    "RunRepository",
    "Scorer",
    "ScorerError",
    "TargetAdapter",
    "TargetAdapterError",
    "TargetExecutor",
    "TaskDefinitionLoader",
    "TaskResourceResolver",
    "TaskRunner",
]

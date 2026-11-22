"""Public report export interface."""

from typing import Protocol, runtime_checkable

from redteam.core.models.report import ReportArtifact, ReportRequest


@runtime_checkable
class ReportExporter(Protocol):
    """Export one persisted task run without changing run records."""

    def export(self, request: ReportRequest) -> tuple[ReportArtifact, ...]:
        """Return one artifact per requested format or raise ReportExportError."""

        ...

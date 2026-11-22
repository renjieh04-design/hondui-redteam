"""Requests and artifacts for V1 report export."""

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Self

from pydantic import Field, PositiveInt, field_validator, model_validator

from redteam.core.models.common import DomainModel, NonEmptyStr
from redteam.core.models.evidence import Sha256Digest


class ReportFormat(StrEnum):
    """Report formats supported by the V1 reporting module."""

    JSON = "json"
    JSONL = "jsonl"
    MARKDOWN = "markdown"


class ReportRequest(DomainModel):
    """A request to export one task run in one or more formats."""

    task_id: NonEmptyStr
    formats: tuple[ReportFormat, ...] = Field(min_length=1)
    output_directory: NonEmptyStr

    @model_validator(mode="after")
    def require_unique_formats(self) -> Self:
        if len(self.formats) != len(set(self.formats)):
            raise ValueError("report formats must be unique")
        return self


class ReportArtifact(DomainModel):
    """Metadata for one report file that was written successfully."""

    task_id: NonEmptyStr
    format: ReportFormat
    path: NonEmptyStr
    media_type: NonEmptyStr
    sha256: Sha256Digest
    size_bytes: PositiveInt
    generated_at: datetime

    @field_validator("generated_at")
    @classmethod
    def require_utc_generated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("generated_at must be a timezone-aware UTC datetime")
        return value

    @model_validator(mode="after")
    def require_matching_media_type(self) -> Self:
        expected_media_types = {
            ReportFormat.JSON: "application/json",
            ReportFormat.JSONL: "application/x-ndjson",
            ReportFormat.MARKDOWN: "text/markdown",
        }
        if self.media_type != expected_media_types[self.format]:
            raise ValueError("report media_type must match its format")
        return self

"""Shared validation primitives for public V1 domain models."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
NormalizedRiskScore = Annotated[float, Field(ge=0.0, le=1.0)]
ErrorMessage = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class DomainModel(BaseModel):
    """The immutable, strict base for public V1 domain models."""

    model_config = ConfigDict(extra="forbid", frozen=True)

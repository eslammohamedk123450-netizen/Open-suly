"""Typed contract shared by isolated SULY engine adapters.

This module defines interfaces and bounded data shapes only. It does not start
engines, grant permissions, or bypass the existing task/tool approval system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class EngineRequest:
    """Minimal task-scoped input sent to an engine adapter.

    Identity claims, approval grants, provider credentials, and database clients
    deliberately do not belong in this payload.
    """

    task_id: str
    capability: str
    input_payload: Mapping[str, Any]
    timeout_seconds: int = 60


@dataclass(frozen=True)
class EngineResult:
    """Bounded, untrusted output returned by an engine adapter."""

    engine_id: str
    output: Mapping[str, Any]


class EngineAdapter(Protocol):
    """Transport-specific adapter implemented by a separately isolated runtime."""

    def execute(self, request: EngineRequest) -> EngineResult:
        """Execute one task-scoped request; caller owns authorization and audit."""
        ...

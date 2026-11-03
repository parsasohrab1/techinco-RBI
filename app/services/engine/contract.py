"""Stable calculation-engine contract used by the analysis service."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from threading import RLock
from typing import Any, ClassVar


@dataclass(frozen=True)
class EngineInputSnapshot:
    equipment_id: int
    component_id: int
    cml_id: int
    inputs: dict[str, Any]
    assumptions: list[dict[str, Any]] = field(default_factory=list)
    data_quality: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineOutput:
    pof_value: float
    pof_category: int
    cof_value: float
    cof_category: str
    risk_score: int
    risk_level: str
    remaining_life_years: float
    recommended_interval_years: float
    intermediate_details: dict[str, Any] = field(default_factory=dict)
    standard_references: list[str] = field(default_factory=list)
    engine_name: str = ""
    engine_version: str = ""
    compliance_status: str = "internal_screening"
    calculated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self) -> None:
        if not isfinite(self.pof_value) or not 0 <= self.pof_value <= 1:
            raise ValueError("POF must be a finite probability between 0 and 1.")
        if not 1 <= self.pof_category <= 5:
            raise ValueError("POF category must be between 1 and 5.")
        if not isfinite(self.cof_value):
            raise ValueError("COF must be finite.")
        if self.cof_category not in {"A", "B", "C", "D", "E"}:
            raise ValueError("COF category must be A through E.")
        if self.risk_score < 1:
            raise ValueError("Risk score must be positive.")
        if self.risk_level not in {"Low", "Medium", "High", "Critical"}:
            raise ValueError("Unsupported risk level.")
        if not isfinite(self.remaining_life_years) or self.remaining_life_years < 0:
            raise ValueError("Remaining life must be finite and non-negative.")
        if (
            not isfinite(self.recommended_interval_years)
            or self.recommended_interval_years <= 0
        ):
            raise ValueError("Recommended interval must be finite and positive.")
        if self.compliance_status not in {
            "internal_screening",
            "under_review",
            "validated",
        }:
            raise ValueError("Unsupported compliance status.")


class ICalculationEngine(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @property
    @abstractmethod
    def supported_mechanisms(self) -> set[str]: ...

    @property
    @abstractmethod
    def compliance_status(self) -> str: ...

    @abstractmethod
    def compute(self, snapshot: EngineInputSnapshot) -> EngineOutput: ...

    def validate_scope(self, mechanism: str) -> None:
        if mechanism.casefold() not in self.supported_mechanisms:
            raise NotImplementedError(
                f"Engine '{self.name}' does not support '{mechanism}'."
            )


class EngineRegistry:
    _engines: ClassVar[dict[str, ICalculationEngine]] = {}
    _lock = RLock()

    @classmethod
    def register(cls, engine: ICalculationEngine) -> None:
        with cls._lock:
            cls._engines[engine.name] = engine

    @classmethod
    def get(cls, name: str) -> ICalculationEngine:
        with cls._lock:
            try:
                return cls._engines[name]
            except KeyError as error:
                raise KeyError(f"Engine '{name}' is not registered.") from error

    @classmethod
    def list_available(cls) -> list[dict[str, Any]]:
        with cls._lock:
            engines = tuple(cls._engines.values())
        return [
            {
                "name": engine.name,
                "version": engine.version,
                "mechanisms": sorted(engine.supported_mechanisms),
                "compliance": engine.compliance_status,
            }
            for engine in engines
        ]


@dataclass(frozen=True)
class EngineConfig:
    engine_name: str
    cof_weights: dict[str, float]
    strict_compliance: bool = False

    def __post_init__(self) -> None:
        required = {"safety", "environmental", "economic"}
        if set(self.cof_weights) != required:
            raise ValueError(f"COF weights must define exactly: {sorted(required)}.")
        if any(not isfinite(weight) or weight < 0 for weight in self.cof_weights.values()):
            raise ValueError("COF weights must be finite and non-negative.")
        if sum(self.cof_weights.values()) <= 0:
            raise ValueError("At least one COF weight must be positive.")

    @classmethod
    def from_settings(cls, settings) -> "EngineConfig":
        return cls(
            engine_name=settings.calculation_engine,
            cof_weights={
                "safety": settings.cof_weight_safety,
                "environmental": settings.cof_weight_environmental,
                "economic": settings.cof_weight_economic,
            },
            strict_compliance=settings.strict_compliance,
        )

    def resolve_engine(self) -> ICalculationEngine:
        engine = EngineRegistry.get(self.engine_name)
        if self.strict_compliance and engine.compliance_status != "validated":
            raise PermissionError(
                f"Strict mode: engine '{engine.name}' is not validated."
            )
        return engine

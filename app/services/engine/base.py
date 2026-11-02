from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from ...models import Component, Equipment


@dataclass
class PofResult:
    value: float
    category: int
    reference: str
    details: dict = field(default_factory=dict)


@dataclass
class CofResult:
    value: float
    category: str
    reference: str
    details: dict = field(default_factory=dict)


@dataclass
class DamageMechanismAssessment:
    mechanism: str
    status: Literal["susceptible", "not_susceptible", "indeterminate"]
    reference: str
    details: dict[str, Any] = field(default_factory=dict)


class IDamageMechanismEvaluator(Protocol):
    mechanism_name: str

    def assess(
        self,
        equipment: "Equipment",
        component: "Component",
        assessment_data: dict[str, bool] | None = None,
    ) -> DamageMechanismAssessment: ...


class IPofCalculator(ABC):
    @abstractmethod
    def calculate(self, component, cml, inspections, active_mechanisms) -> PofResult: ...


class ICofCalculator(ABC):
    @abstractmethod
    def calculate(self, equipment, component) -> CofResult: ...


class IRiskMatrix(ABC):
    @abstractmethod
    def evaluate(self, pof: PofResult, cof: CofResult) -> tuple[int, str]: ...


@dataclass
class EngineMetadata:
    name: str
    version: str
    standard_ref: str


class ICalculationEngine(ABC):
    metadata: EngineMetadata
    pof_calculator: IPofCalculator
    cof_calculator: ICofCalculator
    risk_matrix: IRiskMatrix
    damage_mechanism_evaluators: dict[str, IDamageMechanismEvaluator]

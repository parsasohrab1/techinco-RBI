from abc import ABC, abstractmethod
from dataclasses import dataclass, field


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

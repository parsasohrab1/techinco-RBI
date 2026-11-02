"""Central standard baseline and compliance controls for RBI features."""

from dataclasses import dataclass, field
from enum import Enum


class ComplianceStatus(str, Enum):
    INTERNAL_SCREENING = "internal_screening"
    UNDER_REVIEW = "under_review"
    VALIDATED = "validated"


@dataclass(frozen=True)
class StandardVersion:
    code: str
    edition: str
    year: int
    addendum: str = ""

    def label(self) -> str:
        base = f"{self.code} ({self.edition}, {self.year})"
        return f"{base} + {self.addendum}" if self.addendum else base


API_580 = StandardVersion("API RP 580", "4th", 2023, "Addendum 1 (2025)")
API_581 = StandardVersion("API RP 581", "4th", 2025)
API_571 = StandardVersion("API RP 571", "3rd", 2020)


@dataclass(frozen=True)
class EquipmentScope:
    allowed_types: tuple[str, ...] = (
        "vessel",
        "pressure_vessel",
        "piping",
        "heat_exchanger",
        "atmospheric_tank",
        "pressure_relief_device",
        "boiler",
    )

    def validate(self, equipment_type: str) -> None:
        normalized = equipment_type.strip().casefold().replace("-", "_").replace(" ", "_")
        if normalized not in self.allowed_types:
            raise ValueError(
                f"Equipment type '{equipment_type}' is outside MVP scope. "
                f"Allowed: {self.allowed_types}"
            )


@dataclass
class DamageMechanismScope:
    approved: dict[str, ComplianceStatus] = field(
        default_factory=lambda: {
            "thinning": ComplianceStatus.INTERNAL_SCREENING,
            "cui": ComplianceStatus.INTERNAL_SCREENING,
            "scc": ComplianceStatus.INTERNAL_SCREENING,
            "htha": ComplianceStatus.INTERNAL_SCREENING,
            "brittle_fracture": ComplianceStatus.INTERNAL_SCREENING,
        }
    )

    def require_validated(self, mechanism: str) -> None:
        status = self.approved.get(mechanism, ComplianceStatus.INTERNAL_SCREENING)
        if status != ComplianceStatus.VALIDATED:
            raise PermissionError(
                f"Mechanism '{mechanism}' is {status.value}; cannot be used for compliance claims."
            )


@dataclass(frozen=True)
class AcceptanceCriteria:
    mechanism: str
    reference_case: str | None = None
    tolerance_pct: float | None = None
    independent_test: str | None = None
    signed_off_by: str | None = None

    @property
    def is_complete(self) -> bool:
        return bool(
            self.reference_case
            and self.tolerance_pct is not None
            and self.tolerance_pct >= 0
            and self.independent_test
            and self.signed_off_by
        )


ACCEPTANCE_REGISTRY = {
    name: AcceptanceCriteria(mechanism=name) for name in ("thinning", "cui", "scc")
}


class Baseline:
    api580 = API_580
    api581 = API_581
    api571 = API_571
    equipment_scope = EquipmentScope()
    mechanism_scope = DamageMechanismScope()
    acceptance = ACCEPTANCE_REGISTRY

    @classmethod
    def api580_requirements(cls):
        """Return tracked API 580 mappings, not a complete list of requirements."""
        from .knowledge_base import StandardsKnowledgeBase

        return StandardsKnowledgeBase.by_standard(cls.api580.code)

    @classmethod
    def api581_requirements(cls):
        """Return tracked API 581 mappings, not a complete list of requirements."""
        from .knowledge_base import StandardsKnowledgeBase

        return StandardsKnowledgeBase.by_standard(cls.api581.code)

    @classmethod
    def require_compliance_ready(cls, mechanism: str) -> None:
        cls.mechanism_scope.require_validated(mechanism)
        criteria = cls.acceptance.get(mechanism)
        if criteria is None or not criteria.is_complete:
            raise PermissionError(
                f"Mechanism '{mechanism}' has no complete, signed-off acceptance evidence."
            )

    @classmethod
    def compliance_label(cls) -> str:
        ready = [
            name
            for name, criteria in cls.acceptance.items()
            if criteria.is_complete
            and cls.mechanism_scope.approved.get(name) == ComplianceStatus.VALIDATED
        ]
        if not ready:
            return "INTERNAL SCREENING ONLY — no API conformity claim"
        return f"Validated modules: {', '.join(sorted(ready))} — not full API conformity"

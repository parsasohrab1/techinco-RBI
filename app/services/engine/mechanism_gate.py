"""Admission checks for claims that a damage-mechanism model is validated."""

from dataclasses import dataclass

from ...standards.baseline import (
    ACCEPTANCE_REGISTRY,
    Baseline,
    ComplianceStatus,
)
from ...standards.knowledge_base import StandardsKnowledgeBase


def check_api581_coverage(mechanism: str) -> bool:
    """Whether traceability entries exist; this does not imply model coverage or validation."""
    return bool(StandardsKnowledgeBase.by_mechanism(mechanism))


@dataclass(frozen=True)
class MechanismAdmission:
    mechanism: str
    validated: bool
    reference_case: str | None
    independent_test: str | None
    blockers: list[str]


class MechanismGate:
    @staticmethod
    def check(mechanism: str) -> MechanismAdmission:
        normalized = mechanism.casefold()
        status = Baseline.mechanism_scope.approved.get(
            normalized,
            ComplianceStatus.INTERNAL_SCREENING,
        )
        criteria = ACCEPTANCE_REGISTRY.get(normalized)
        blockers = []

        if status != ComplianceStatus.VALIDATED:
            blockers.append(f"status={status.value}")
        if criteria is None:
            blockers.append("no acceptance criteria registered")
        else:
            if not criteria.reference_case:
                blockers.append("no approved reference case")
            if criteria.tolerance_pct is None or criteria.tolerance_pct < 0:
                blockers.append("no valid acceptance tolerance")
            if not criteria.independent_test:
                blockers.append("no independent test")
            if not criteria.signed_off_by:
                blockers.append("not signed off by a domain expert")

        return MechanismAdmission(
            mechanism=normalized,
            validated=not blockers,
            reference_case=criteria.reference_case if criteria else None,
            independent_test=criteria.independent_test if criteria else None,
            blockers=blockers,
        )

    @staticmethod
    def assert_admitted(mechanism: str) -> None:
        admission = MechanismGate.check(mechanism)
        if not admission.validated:
            raise PermissionError(
                f"Mechanism '{admission.mechanism}' blocked: "
                f"{', '.join(admission.blockers)}"
            )

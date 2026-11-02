"""Structured, deliberately partial traceability for implemented RBI features."""

from dataclasses import asdict, dataclass
from typing import ClassVar


@dataclass(frozen=True)
class TraceabilityEntry:
    standard: str
    section: str
    title: str
    implementation: str
    status: str
    acceptance_evidence: str
    limitation: str
    mechanisms: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, str | list[str]]:
        entry = asdict(self)
        entry["mechanisms"] = list(self.mechanisms)
        return entry


class StandardsKnowledgeBase:
    """Queryable index of this product's traceability, not a standards database."""

    _entries: ClassVar[tuple[TraceabilityEntry, ...]] = (
        TraceabilityEntry(
            "API RP 580",
            "§8",
            "Data sources and quality",
            "DataQualityStatus; DataPlatformService.require_analysis_quality",
            "Implemented for analysis-gating inputs",
            "Tests verify missing/unverified required evidence blocks analysis.",
            "Provenance records do not independently verify source data.",
        ),
        TraceabilityEntry(
            "API RP 580",
            "§8.3",
            "Engineering assumptions",
            "EngineeringAssumption; DataPlatformService",
            "Partial",
            "Approved assumptions are applied to supported inputs and captured in snapshots.",
            "Approver identity is caller-supplied; authentication and independent approval are absent.",
        ),
        TraceabilityEntry(
            "API RP 580",
            "§12",
            "Approval and change records",
            "ApprovalWorkflow; TraceableEvent; data-platform router",
            "Partial",
            "Workflow decisions emit traceable events.",
            "Entity changes are not universally approval-gated; records are not tamper-proof.",
        ),
        TraceabilityEntry(
            "API RP 580",
            "§13",
            "Inspection planning and CMMS boundary",
            "InspectionWorkPackage; CmmsPort",
            "Port and unvalidated stubs",
            "Package represents equipment, CML, method, target date, priority, mechanisms, and risk.",
            "Enterprise transports are unimplemented and the port is not wired to the mock CMMS endpoint.",
        ),
        TraceabilityEntry(
            "API RP 580",
            "§16",
            "Analysis reconstruction",
            "AuditReconstructionReport",
            "Partial",
            "Endpoint reports persisted inputs, assumptions, quality, calculation details, and results.",
            "Report does not recalculate results and audit records are not immutable.",
        ),
        TraceabilityEntry(
            "API RP 581",
            "Part 2",
            "Thinning probability screen",
            "InternalPofCalculator",
            "Internal screening only",
            "Proxy behavior and output shape are tested.",
            "No approved independent reference case or expert sign-off is registered.",
            ("thinning",),
        ),
        TraceabilityEntry(
            "API RP 581",
            "Part 2",
            "CUI susceptibility screen",
            "CUIDamageMechanismEvaluator",
            "Susceptibility screen only",
            "Susceptibility evaluator behavior is tested.",
            "No CUI POF calculator or approved independent reference case is implemented.",
            ("cui",),
        ),
        TraceabilityEntry(
            "API RP 581",
            "Part 3",
            "Consequence screen",
            "InternalCofCalculator",
            "Illustrative internal score",
            "Configurable safety, environmental, and economic weights are exercised by tests.",
            "This is not a validated physical consequence model.",
        ),
        TraceabilityEntry(
            "API RP 581",
            "Part 4",
            "Inspection interval recommendation",
            "analysis_orchestrator.recommended_interval",
            "Internal screening recommendation",
            "End-to-end tests exercise recommendation output.",
            "Not a validated inspection method, scope, or due-date plan.",
        ),
        TraceabilityEntry(
            "API RP 571",
            "Damage mechanism catalog",
            "Mechanism references and screening",
            "DamageMechanism; damage_mechanisms service",
            "Catalog and simplified screens",
            "Catalog metadata and screen behavior are covered by tests.",
            "Mechanism evaluators are not validated standard models.",
        ),
        TraceabilityEntry(
            "SRS",
            "FR-CALC-05 / FR-CALC-06",
            "Calculation engine contract",
            "ICalculationEngine; EngineRegistry; InternalEngine",
            "Implemented for internal screening",
            "Contract execution, output validation, and strict-mode rejection are tested.",
            "The registered calculation implementation is not validated against approved reference cases.",
        ),
    )

    @classmethod
    def all_entries(cls) -> list[TraceabilityEntry]:
        return list(cls._entries)

    @classmethod
    def by_standard(cls, standard: str) -> list[TraceabilityEntry]:
        normalized = standard.strip().casefold()
        return [entry for entry in cls._entries if entry.standard.casefold() == normalized]

    @classmethod
    def by_mechanism(cls, mechanism: str) -> list[TraceabilityEntry]:
        normalized = mechanism.strip().casefold()
        return [
            entry
            for entry in cls._entries
            if normalized in entry.mechanisms
        ]

    @classmethod
    def traceability_matrix(cls) -> list[dict[str, str | list[str]]]:
        return [entry.as_dict() for entry in cls._entries]

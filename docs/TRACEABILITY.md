# RBI requirements and implementation traceability

This table maps requested standards topics to the current product implementation.
It is a project traceability aid, not a reproduction of any standard, independent
verification, certification, or claim of conformity. Clause identifiers and
summaries must be checked against the organization's licensed editions and RBI
basis before use.

| Standard reference | Topic | Code module | Current status | Acceptance evidence / limitation |
|---|---|---|---|---|
| API RP 580 §8 | Data sources and quality | `app/models_data_platform.py::DataQualityStatus`; `app/services/data_platform.py::require_analysis_quality` | Implemented for analysis-gating inputs | `tests/test_api.py::test_full_workflow` proves missing or unverified required evidence blocks analysis with HTTP 409. This is field-level provenance, not automatic data verification. |
| API RP 580 §8.3 | Engineering assumptions | `app/models_data_platform.py::EngineeringAssumption`; `app/services/data_platform.py` | Implemented, partial | Assumptions require a basis, caller-supplied actor approval, and an active quality record. Approved values are parsed, applied to supported calculation inputs, and stored in the analysis snapshot. There is no authentication/authorization or independent approver enforcement yet. |
| API RP 580 §12 | Approval and change records | `app/models_data_platform.py::ApprovalWorkflow`; `TraceableEvent`; `app/routers/data_platform.py` | Partial | Workflow transitions and events are tested in `tests/test_data_platform.py`. Existing entity edits are not universally gated by approval, and these events are not tamper-proof or hash-chained. |
| API RP 580 §13 | Inspection planning package and CMMS boundary | `app/integrations/cmms_port.py::InspectionWorkPackage`; `CmmsPort`; `CmmsIntegrationService` | Port and unvalidated stubs only | Package shape carries equipment, CML, method, target date, priority, mechanisms, risk, and references. SAP PM/Maximo transport is deliberately unimplemented and rejected unless an adapter reports validated. This port is not yet wired to the existing mock CMMS endpoint. |
| API RP 580 §16 | Analysis reconstruction and records | `app/services/audit_report.py::AuditReconstructionReport`; `app/routers/audit_router.py` | Implemented, partial | `GET /audit/runs/{run_id}/reconstruction` returns stored input, assumptions, quality evidence, calculation details, results, and limitations. It reconstructs persisted data; it does not independently rerun calculations and is not an immutable audit store. |
| API RP 581 Part 2 | Thinning probability screen | `app/services/engine/impl_internal.py::InternalPofCalculator` | Internal screening only | `tests/test_thinning.py` checks proxy behavior and output shape. No approved independent `REF-THIN-001` data or sign-off is present; these tests do not establish standard conformance. |
| API RP 581 Part 2 | CUI probability of failure | `app/services/engine/damage_mechanisms.py::CUIDamageMechanismEvaluator` | Susceptibility screen only; no CUI POF calculator | Current module only returns a generic susceptibility screen. The proposed `REF-CUI-001` values have not been independently verified or signed off, so no reference-value test or API 581 claim is made. |
| API RP 581 Part 3 | Consequence screen | `app/services/engine/impl_internal.py::InternalCofCalculator` | Illustrative internal score | Safety, environmental, and economic scores use configurable weights. The implementation is not a validated physical consequence model. |
| API RP 581 Part 4 | Inspection interval recommendation | `app/services/analysis_orchestrator.py::recommended_interval`; `app/services/engine/impl_internal.py::_recommended_interval` | Internal screening recommendation | Existing tests exercise end-to-end output. This is not a validated method/scope/due-date work plan. |
| API RP 571 | Damage mechanism catalog and screening | `app/models.py::DamageMechanism`; `app/services/engine/damage_mechanisms.py` | Catalog and simplified screens | Mechanism references are catalog metadata. CUI and SCC evaluators are not validated API RP 571 models. |
| SRS FR-CALC-05 / FR-CALC-06 | Pluggable engine metadata and results | `app/services/engine/contract.py`; `app/services/analysis_orchestrator.py` | Implemented for the internal engine | `tests/test_engine_contract.py` verifies contract execution, output validation, engine registry, and strict-mode rejection. The only registered production implementation is internal screening. |
| SRS §4 | Mechanism validation admission | `app/services/engine/mechanism_gate.py`; `app/standards/baseline.py` | Gate implemented; all current mechanisms blocked from validated claims | `tests/test_engine_contract.py::test_mechanism_gate_blocks_unverified_reference_cases` confirms no current mechanism is admitted without reference, test, tolerance, and expert sign-off evidence. |

## Status rules

- **Internal screening** means illustrative behavior that is not validated against
  approved independent cases.
- **Under review** requires a documented review process and does not imply
  validation.
- **Validated** requires an approved reference case, independent test, defined
  acceptance tolerance, and domain-expert sign-off. Updating a status alone is
  insufficient; strict mode also checks the admission gate.

Do not use the internal engine, its recommended intervals, or the stub adapters
as the sole basis for safety-critical inspection or regulatory submissions.

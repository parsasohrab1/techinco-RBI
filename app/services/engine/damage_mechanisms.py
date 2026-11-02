from ... import models
from .base import DamageMechanismAssessment


class CUIDamageMechanismEvaluator:
    mechanism_name = "CUI"
    minimum_temperature_c = -12.0
    maximum_temperature_c = 175.0
    reference = "API 571 §4.3.1 (simplified temperature screening)"

    def assess(
        self,
        equipment: models.Equipment,
        component: models.Component,
        assessment_data: dict[str, bool] | None = None,
    ) -> DamageMechanismAssessment:
        temperature = component.operating_temperature_c
        details = {
            "insulated": component.insulated,
            "operating_temperature_c": temperature,
            "screening_range_c": {
                "minimum": self.minimum_temperature_c,
                "maximum": self.maximum_temperature_c,
            },
            "material": equipment.material,
            "assessment_type": "susceptibility_screen_only",
        }

        if not component.insulated:
            status = "not_susceptible"
            details["reason"] = "component_not_insulated"
        elif not self._uses_carbon_or_low_alloy_steel(equipment.material):
            status = "indeterminate"
            details["reason"] = "material_outside_supported_screen"
        elif temperature is None:
            status = "indeterminate"
            details["reason"] = "operating_temperature_missing"
        elif self.minimum_temperature_c <= temperature <= self.maximum_temperature_c:
            status = "susceptible"
            details["reason"] = "insulated_steel_within_screening_temperature_range"
        else:
            status = "not_susceptible"
            details["reason"] = "operating_temperature_outside_screening_range"

        return DamageMechanismAssessment(
            mechanism=self.mechanism_name,
            status=status,
            reference=self.reference,
            details=details,
        )

    @staticmethod
    def _uses_carbon_or_low_alloy_steel(material: str) -> bool:
        normalized = " ".join(material.casefold().replace("-", " ").split())
        return (
            "carbon steel" in normalized
            or "low alloy steel" in normalized
            or normalized in {"cs", "las"}
        )


class SCCChecklistEvaluator:
    mechanism_name = "SCC"
    required_inputs = (
        "susceptible_material",
        "environment_present",
        "tensile_stress_present",
    )
    reference = "Internal generic screening checklist (not API 571/581)"

    def assess(
        self,
        equipment: models.Equipment,
        component: models.Component,
        assessment_data: dict[str, bool] | None = None,
    ) -> DamageMechanismAssessment:
        inputs = assessment_data or {}
        missing = [key for key in self.required_inputs if key not in inputs]
        if missing:
            status = "indeterminate"
            reason = "required_screening_inputs_missing"
        elif all(inputs[key] for key in self.required_inputs):
            status = "susceptible"
            reason = "all_generic_screening_conditions_reported_present"
        else:
            status = "not_susceptible"
            reason = "one_or_more_generic_screening_conditions_reported_absent"

        return DamageMechanismAssessment(
            mechanism=self.mechanism_name,
            status=status,
            reference=self.reference,
            details={
                "assessment_type": "generic_user_input_checklist_only",
                "inputs": inputs,
                "required_inputs": list(self.required_inputs),
                "missing_inputs": missing,
                "reason": reason,
                "limitations": (
                    "This checklist is not a mechanism-specific susceptibility model, "
                    "does not calculate cracking likelihood, and is not API-conforming."
                ),
            },
        )

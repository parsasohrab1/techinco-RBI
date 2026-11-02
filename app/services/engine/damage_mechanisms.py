from ... import models
from .base import DamageMechanismAssessment


class CUIDamageMechanismEvaluator:
    mechanism_name = "CUI"
    minimum_temperature_c = -12.0
    maximum_temperature_c = 175.0
    reference = "API 571 §4.3.1 (simplified temperature screening)"

    def assess(
        self, equipment: models.Equipment, component: models.Component
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

"""Replaceable CMMS port; external adapters remain disabled until validated."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InspectionWorkPackage:
    equipment_tag: str
    cml_id: int
    method: str
    target_date: str
    priority: str
    damage_mechanisms: list[str]
    risk_level: str
    standard_refs: list[str]


class CmmsPort(ABC):
    @abstractmethod
    def push_work_package(self, package: InspectionWorkPackage) -> str: ...

    @abstractmethod
    def pull_equipment_master(self, since: str | None = None) -> list[dict[str, Any]]: ...

    @abstractmethod
    def health(self) -> dict[str, Any]: ...


class _UnvalidatedEnterpriseAdapter(CmmsPort):
    adapter_name = "unvalidated"

    def _not_validated(self) -> None:
        raise NotImplementedError(
            f"{self.adapter_name} adapter transport and mapping are not validated."
        )

    def push_work_package(self, package: InspectionWorkPackage) -> str:
        self._not_validated()

    def pull_equipment_master(self, since: str | None = None) -> list[dict[str, Any]]:
        self._not_validated()


class SapPmAdapter(_UnvalidatedEnterpriseAdapter):
    adapter_name = "sap_pm"

    def __init__(self, base_url: str, auth_token: str):
        self.base_url = base_url
        self._auth_token = auth_token

    def health(self) -> dict[str, Any]:
        return {"adapter": self.adapter_name, "status": "stub", "validated": False}


class MaximoAdapter(_UnvalidatedEnterpriseAdapter):
    adapter_name = "maximo"

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self._api_key = api_key

    def health(self) -> dict[str, Any]:
        return {"adapter": self.adapter_name, "status": "stub", "validated": False}


class CmmsIntegrationService:
    def __init__(self, adapter: CmmsPort):
        self.adapter = adapter

    def push_plan(self, packages: list[InspectionWorkPackage]) -> list[str]:
        health = self.adapter.health()
        if health.get("validated") is not True:
            raise PermissionError(
                f"CMMS adapter {health.get('adapter', 'unknown')} is not validated "
                f"({health.get('status', 'unknown')}); work packages cannot be pushed."
            )
        return [self.adapter.push_work_package(package) for package in packages]

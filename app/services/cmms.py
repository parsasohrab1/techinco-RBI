from dataclasses import dataclass
from threading import Lock
from typing import Protocol


@dataclass(frozen=True)
class CMMSConnectionStatus:
    adapter: str
    mode: str
    connected: bool
    message: str


@dataclass(frozen=True)
class WorkOrderRequest:
    external_reference: str
    asset_number: str
    location: str
    risk_level: str
    risk_score: int
    summary: str
    recommended_interval_years: float


@dataclass(frozen=True)
class WorkOrderReceipt:
    external_reference: str
    work_order_id: str
    status: str
    created: bool
    asset_number: str
    location: str
    risk_level: str
    risk_score: int
    summary: str
    recommended_interval_years: float


class CMMSAdapter(Protocol):
    adapter_name: str

    def health(self) -> CMMSConnectionStatus: ...

    def create_work_order(self, work_order: WorkOrderRequest) -> WorkOrderReceipt: ...


class MockMaximoClient:
    adapter_name = "sap-maximo-mock"

    def __init__(self) -> None:
        self._lock = Lock()
        self._work_orders: dict[str, WorkOrderReceipt] = {}

    def health(self) -> CMMSConnectionStatus:
        return CMMSConnectionStatus(
            adapter=self.adapter_name,
            mode="mock",
            connected=True,
            message="Mock adapter is ready; no external CMMS is contacted.",
        )

    def create_work_order(self, work_order: WorkOrderRequest) -> WorkOrderReceipt:
        with self._lock:
            existing = self._work_orders.get(work_order.external_reference)
            if existing is not None:
                return WorkOrderReceipt(
                    external_reference=existing.external_reference,
                    work_order_id=existing.work_order_id,
                    status="already_exists",
                    created=False,
                    asset_number=existing.asset_number,
                    location=existing.location,
                    risk_level=existing.risk_level,
                    risk_score=existing.risk_score,
                    summary=existing.summary,
                    recommended_interval_years=existing.recommended_interval_years,
                )

            receipt = WorkOrderReceipt(
                external_reference=work_order.external_reference,
                work_order_id=f"MOCK-WO-{len(self._work_orders) + 1:06d}",
                status="created",
                created=True,
                asset_number=work_order.asset_number,
                location=work_order.location,
                risk_level=work_order.risk_level,
                risk_score=work_order.risk_score,
                summary=work_order.summary,
                recommended_interval_years=work_order.recommended_interval_years,
            )
            self._work_orders[work_order.external_reference] = receipt
            return receipt


_mock_maximo_client = MockMaximoClient()


def get_cmms_adapter() -> CMMSAdapter:
    return _mock_maximo_client

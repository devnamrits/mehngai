from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NewObservation:
    chain: str
    raw_name: str
    brand: str | None
    pack_size: str | None
    price: float | None
    currency: str
    unit_price: float | None
    unit_label: str | None
    url: str | None
    collected_at: datetime | None = None


@dataclass(frozen=True)
class RunSummary:
    id: int
    collector_id: str
    chain: str
    row_count: int
    status: str


@dataclass(frozen=True)
class PriceRow:
    chain: str
    raw_name: str
    canonical_name: str
    price: float | None
    unit_price: float | None
    unit_label: str | None
    url: str | None
    collected_at: datetime


class Repository(ABC):
    @abstractmethod
    def start_run(self, collector_id: str, chain: str) -> int: ...

    @abstractmethod
    def finish_run(self, run_id: int, row_count: int, status: str) -> None: ...

    @abstractmethod
    def insert_observations(self, run_id: int, observations: list[NewObservation]) -> int: ...

    @abstractmethod
    def open_incident(self, collector_id: str, reason: str, heal_prompt: str | None = None) -> int: ...

    @abstractmethod
    def resolve_incident(self, incident_id: int, outcome: str) -> None: ...

    @abstractmethod
    def save_index_point(self, day: str, scope: str, value: float) -> None: ...

    @abstractmethod
    def latest_base_price(self, chain: str, canonical_id: int): ...

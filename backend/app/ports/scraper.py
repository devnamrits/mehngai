from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class HealRequest:
    collector_id: str
    prompt: str
    url: str | None = None
    auto_approve: bool = False


@dataclass(frozen=True)
class HealResult:
    approved: bool
    status: str
    detail: str


class ScraperStudioPort(ABC):
    @abstractmethod
    def trigger_and_collect(self, collector_id: str, url: str | None) -> list[dict]:
        """Trigger a collector run and return raw rows once the snapshot completes."""

    @abstractmethod
    def heal(self, request: HealRequest) -> HealResult:
        """Repair a broken collector in place; Collector ID must remain unchanged."""

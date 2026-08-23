from datetime import datetime, timezone

from app.adapters.repository_sql import SqlRepository
from app.core.config import Settings
from app.ports.repository import NewObservation, Repository
from app.ports.scraper import HealRequest, ScraperStudioPort
from app.services.index_engine import IndexEngine
from app.services.normalizer import compute_unit_price
from app.services.pulse import PulseBus
from app.services.validators import CollectorContract, Verdict, run_validators


class OrchestratorService:
    def __init__(
        self,
        scraper: ScraperStudioPort,
        repository_factory,
        settings: Settings,
        pulse: PulseBus,
    ) -> None:
        self._scraper = scraper
        self._repository_factory = repository_factory
        self._settings = settings
        self._pulse = pulse
        self._graduated: set[str] = set()

    @property
    def contracts(self) -> list[CollectorContract]:
        labels = ["A", "B", "C", "D", "E"]
        return [
            CollectorContract(
                collector_id=collector_id,
                chain=f"chain-{labels[i % len(labels)]}",
                required_fields=("title", "price"),
            )
            for i, collector_id in enumerate(self._settings.collectors)
        ]

    def run_nightly(self) -> dict:
        day = datetime.now(timezone.utc).date().isoformat()
        summary: dict = {"day": day, "runs": [], "healed": []}
        contracts = self.contracts
        if not contracts:
            self._pulse.emit("error", "config", "no collectors configured")
            return summary

        self._pulse.emit("info", "pipeline", f"nightly run starting ({len(contracts)} chains)")
        for contract in contracts:
            result = self._run_chain(contract)
            summary["runs"].append(result)
            if result.get("healed"):
                summary["healed"].append(contract.chain)

        with self._repository_factory() as repo_session:
            values = IndexEngine(repo_session).compute_for_day(day)
        summary["index"] = values
        self._pulse.emit("info", "pipeline", f"nightly complete: {values}")
        return summary

    def _run_chain(self, contract: CollectorContract) -> dict:
        healed = False
        rows = self._collect(contract)
        verdicts = run_validators(rows, contract)
        critical = [v for v in verdicts if v.is_critical]

        if critical and rows is not None:
            healed = self._attempt_heal(contract, critical)
            if healed:
                rows = self._collect(contract)
                retry_critical = [v for v in run_validators(rows, contract) if v.is_critical]
                healed = not retry_critical

        status = "ok"
        if healed:
            status = "healed"
        elif rows == []:
            status = "failed"

        stored = 0
        with self._repository_factory() as repo_session:
            repository: Repository = SqlRepository(repo_session)
            run_id = repository.start_run(contract.collector_id, contract.chain)
            stored = repository.insert_observations(run_id, to_observations(rows, contract.chain))
            repository.finish_run(run_id, stored, status)
        self._pulse.emit("info", "ingest", f"{contract.chain}: stored {stored} rows ({status})")

        return {"chain": contract.chain, "collector": contract.collector_id, "rows": stored, "status": status, "healed": healed}

    def _collect(self, contract: CollectorContract) -> list[dict]:
        try:
            return self._scraper.trigger_and_collect(contract.collector_id, None)
        except Exception as exc:
            self._pulse.emit("error", "collect", f"{contract.chain}: {exc}")
            return []

    def _attempt_heal(self, contract: CollectorContract, critical: list[Verdict]) -> bool:
        reason = "; ".join(v.detail for v in critical)
        prompt = self._heal_prompt(contract, critical)
        with self._repository_factory() as repo_session:
            SqlRepository(repo_session).open_incident(contract.collector_id, reason, prompt)

        auto_approve = contract.collector_id in self._graduated
        self._pulse.emit(
            "warn" if not auto_approve else "heal",
            "watchdog",
            f"{contract.chain} drift: {reason} -> heal dispatched (auto={auto_approve})",
        )
        try:
            result = self._scraper.heal(
                HealRequest(collector_id=contract.collector_id, prompt=prompt, auto_approve=auto_approve)
            )
        except Exception as exc:
            self._pulse.emit("error", "watchdog", f"{contract.chain}: heal failed {exc}")
            return False
        if result.approved:
            self._graduated.add(contract.collector_id)
            self._pulse.emit("heal", "watchdog", f"{contract.chain}: heal applied, same Collector ID")
        return bool(result.approved)

    @staticmethod
    def _heal_prompt(contract: CollectorContract, critical: list[Verdict]) -> str:
        fields = sorted({v.detail.split('"')[1] for v in critical if '"' in v.detail})
        target = ", ".join(fields) or "the main fields"
        return (
            f"The scraper for {contract.chain} started returning empty/null values for {target} "
            f"since the site layout changed. Re-capture these fields from the current markup "
            f"while keeping the exact same output schema."
        )[:1000]



def to_observations(rows: list[dict], chain: str, collected_at=None) -> list[NewObservation]:
    observations: list[NewObservation] = []
    for row in rows:
        raw_name = str(row.get("title") or row.get("name") or "").strip()
        if not raw_name:
            continue
        price = _as_float(row.get("price"))
        pack_size = row.get("pack_size") or row.get("packSize")
        unit = compute_unit_price(price, str(pack_size) if pack_size else None, raw_name)
        observations.append(
            NewObservation(
                chain=chain,
                raw_name=raw_name,
                brand=row.get("brand"),
                pack_size=str(pack_size) if pack_size else None,
                price=price,
                currency=str(row.get("currency") or "INR"),
                unit_price=unit.value,
                unit_label=unit.label,
                url=row.get("url"),
                collected_at=collected_at,
            )
        )
    return observations


def _as_float(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        cleaned = str(value).replace(",", "").strip()
        return float(cleaned) if cleaned else None
    except ValueError:
        return None

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
        self._heal_cooldown: dict[str, float] = {}

    @property
    def contracts(self) -> list[CollectorContract]:
        labels = ["a", "b", "c", "d", "e"]
        urls = self._settings.collector_url_list
        return [
            CollectorContract(
                collector_id=collector_id,
                chain=f"chain-{labels[i % len(labels)]}",
                required_fields=("title", "price"),
                target_url=urls[i] if i < len(urls) else None,
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
        collected_ok = True
        rows, collected_ok = self._collect(contract)
        rows = [project_row(r) for r in rows]
        verdicts = run_validators(rows, contract) if collected_ok else []
        critical = [v for v in verdicts if v.is_critical]

        if critical and collected_ok:
            healed = self._attempt_heal(contract, critical)
            if healed:
                rows, _ = self._collect(contract)
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

    def _collect(self, contract: CollectorContract) -> tuple[list[dict], bool]:
        try:
            rows = self._scraper.trigger_and_collect(contract.collector_id, contract.target_url)
            return flatten_rows(rows), True
        except Exception as exc:
            self._pulse.emit("error", "collect", f"{contract.chain}: {exc}")
            return [], False

    def _attempt_heal(self, contract: CollectorContract, critical: list[Verdict]) -> bool:
        reason = "; ".join(v.detail for v in critical)
        prompt = self._heal_prompt(contract, critical)
        with self._repository_factory() as repo_session:
            SqlRepository(repo_session).open_incident(contract.collector_id, reason, prompt)

        import time as _time
        now = _time.monotonic()
        last = self._heal_cooldown.get(contract.collector_id, 0)
        if now - last < 1800:
            self._pulse.emit("warn", "watchdog",
                             f"{contract.chain}: heal skipped (cooldown)")
            return False
        self._heal_cooldown[contract.collector_id] = now
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



_LIST_KEYS = ("product_listings", "products", "items")


def flatten_rows(rows: list[dict]) -> list[dict]:
    flat: list[dict] = []
    for row in rows:
        exploded = False
        for key in _LIST_KEYS:
            listings = row.get(key)
            if isinstance(listings, list) and listings and all(isinstance(x, dict) for x in listings):
                flat.extend(listings)
                exploded = True
                break
        if not exploded:
            flat.append(row)
    return flat


def project_row(row: dict) -> dict:
    """Project any collector's dialect onto the canonical schema BEFORE validation."""
    return {
        "title": _first(row, "title", "product_title", "name"),
        "price": _extract_price(row),
        "pack_size": _first(row, "pack_size", "pack_size_label", "weight"),
        "brand": _first(row, "brand", "brand_name"),
        "url": _first(row, "url", "product_page_url", "product_url", "link"),
    }


def _first(row: dict, *keys):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _extract_price(row: dict) -> float | None:
    for key in ("price", "selling_price", "final_price"):
        value = row.get(key)
        if isinstance(value, dict):
            value = value.get("value")
        if value is None or value == "":
            continue
        parsed = _as_float(value)
        if parsed is not None:
            return parsed
    return None


def to_observations(rows: list[dict], chain: str, collected_at=None) -> list[NewObservation]:
    observations: list[NewObservation] = []
    for row in rows:
        raw_name = str(_first(row, "title", "product_title", "name") or "").strip()
        if not raw_name:
            continue
        price = _extract_price(row)
        pack_size = _first(row, "pack_size", "pack_size_label", "weight")
        unit = compute_unit_price(price, str(pack_size) if pack_size else None, raw_name)
        observations.append(
            NewObservation(
                chain=chain,
                raw_name=raw_name,
                brand=_first(row, "brand", "brand_name"),
                pack_size=str(pack_size) if pack_size else None,
                price=price,
                currency="INR",
                unit_price=unit.value,
                unit_label=unit.label,
                url=_first(row, "url", "product_page_url", "product_url", "link"),
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

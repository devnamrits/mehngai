import math
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import IndexPoint, Item, Observation, Run


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


class IndexEngine:
    def __init__(self, session: Session) -> None:
        self._session = session

    def compute_for_day(self, day: str) -> dict[str, float]:
        rows = self._session.execute(
            select(Run.chain, Observation.canonical_id, Observation.unit_price)
            .join(Run, Run.id == Observation.run_id)
            .where(
                func.date(Observation.collected_at) == day,
                Observation.unit_price.is_not(None),
                Observation.unit_price > 0,
                Observation.canonical_id.is_not(None),
            )
        ).all()

        grouped: dict[str, dict[int, list[float]]] = {}
        for chain, item_id, unit_price in rows:
            grouped.setdefault(chain, {}).setdefault(item_id, []).append(unit_price)

        medians: dict[str, float] = {}
        counts: dict[str, int] = {}
        for chain, items in grouped.items():
            for item_id, prices in items.items():
                key = f"{chain}:{item_id}"
                medians[key] = _median(prices)
            counts[chain] = len(items)

        results: dict[str, float] = {}
        for chain in grouped:
            previous = self._latest_value_before(day, chain)
            value = 100.0 if previous is None else round(previous * self._ratio(chain, medians), 4)
            if not math.isfinite(value) or value <= 0:
                continue
            results[chain] = value
            self._session.merge(IndexPoint(day=day, scope=chain, value=value))

        if grouped:
            blend = sum(results.values()) / len(results)
            results["blend"] = round(blend, 4)
            self._session.merge(IndexPoint(day=day, scope="blend", value=results["blend"]))
            counts.pop("blend", None)

        self._session.flush()
        return results

    def _ratio(self, chain: str, medians: dict[str, float]) -> float:
        numerator = 0.0
        denominator = 0.0
        prefix = f"{chain}:"
        for key, median in medians.items():
            if not key.startswith(prefix):
                continue
            raw_id = key.split(":", 1)[1]
            if not raw_id.isdigit():
                continue
            item_id = int(raw_id)
            base_price = self._base_price(chain, item_id)
            if base_price and base_price > 0 and median > 0:
                numerator += median
                denominator += base_price
        return numerator / denominator if denominator else 1.0

    def _base_price(self, chain: str, item_id: int) -> float | None:
        first_id = self._session.scalar(
            select(Observation.id)
            .join(Run, Run.id == Observation.run_id)
            .where(
                Run.chain == chain,
                Observation.canonical_id == item_id,
                Observation.unit_price.is_not(None),
                Observation.unit_price > 0,
            )
            .order_by(Observation.id.asc())
            .limit(1)
        )
        if first_id is None:
            return None
        return self._session.scalar(select(Observation.unit_price).where(Observation.id == first_id))

    def _latest_value_before(self, day: str, scope: str) -> float | None:
        value = self._session.scalar(
            select(IndexPoint.value)
            .where(IndexPoint.scope == scope, IndexPoint.day < day)
            .order_by(IndexPoint.day.desc())
            .limit(1)
        )
        return value

    def series(self, days: int = 30, scope: str | None = None):
        query = select(IndexPoint).order_by(IndexPoint.day.asc())
        if scope:
            query = query.where(IndexPoint.scope == scope)
        points = self._session.scalars(query).all()
        return [
            {"day": p.day, "scope": p.scope, "value": p.value, "method": p.method}
            for p in points[-days * 8 :]
        ]

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import Incident, IndexPoint, Item, Observation, Run, utcnow
from app.ports.repository import NewObservation, Repository
from app.services.normalizer import guess_category, normalize_name


class SqlRepository(Repository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def start_run(self, collector_id: str, chain: str) -> int:
        run = Run(collector_id=collector_id, chain=chain)
        self._session.add(run)
        self._session.flush()
        return run.id

    def finish_run(self, run_id: int, row_count: int, status: str) -> None:
        run = self._session.get(Run, run_id)
        if run:
            run.row_count = row_count
            run.status = status

    def insert_observations(self, run_id: int, observations: list[NewObservation]) -> int:
        count = 0
        for obs in observations:
            canonical_id = self._ensure_item(obs.raw_name)
            self._session.add(
                Observation(
                    run_id=run_id,
                    chain=obs.chain,
                    raw_name=obs.raw_name,
                    canonical_id=canonical_id,
                    brand=obs.brand,
                    pack_size=obs.pack_size,
                    price=obs.price,
                    currency=obs.currency,
                    unit_price=obs.unit_price,
                    unit_label=obs.unit_label,
                    url=obs.url,
                    collected_at=obs.collected_at or utcnow(),
                )
            )
            count += 1
        self._session.flush()
        return count

    def _ensure_item(self, raw_name: str) -> int | None:
        canonical = normalize_name(raw_name)
        if not canonical:
            return None
        item = self._session.scalar(select(Item).where(Item.canonical_name == canonical))
        if item is None:
            item = Item(canonical_name=canonical, category=guess_category(raw_name))
            self._session.add(item)
            self._session.flush()
        return item.id

    def open_incident(self, collector_id: str, reason: str, heal_prompt: str | None = None) -> int:
        incident = Incident(collector_id=collector_id, reason=reason, heal_prompt=heal_prompt)
        self._session.add(incident)
        self._session.flush()
        return incident.id

    def resolve_incident(self, incident_id: int, outcome: str) -> None:
        incident = self._session.get(Incident, incident_id)
        if incident:
            incident.resolved_at = utcnow()
            incident.outcome = outcome

    def save_index_point(self, day: str, scope: str, value: float) -> None:
        existing = self._session.get(IndexPoint, (day, scope))
        if existing:
            existing.value = value
        else:
            self._session.add(IndexPoint(day=day, scope=scope, value=value))
        self._session.flush()

    def latest_base_price(self, chain: str, canonical_id: int):
        subq = (
            select(func.min(Observation.id))
            .join(Run, Run.id == Observation.run_id)
            .where(
                Run.chain == chain,
                Observation.canonical_id == canonical_id,
                Observation.unit_price.is_not(None),
            )
            .correlate(Observation)
            .scalar_subquery()
        )
        return self._session.scalar(
            select(Observation.unit_price).where(Observation.id == subq)
        )

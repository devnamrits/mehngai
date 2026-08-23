from contextlib import contextmanager

from app.services.index_engine import IndexEngine
from app.services.orchestrator import OrchestratorService
from tests.conftest import FakeScraper


@contextmanager
def repo_factory(session):
    yield session


def seed_day(session, chain: str, day: str, prices: list[float]):
    from datetime import datetime

    from app.domain.models import Item, Observation, Run

    r = Run(collector_id=f"c_{chain}", chain=chain, status="ok")
    session.add(r)
    session.flush()
    for i, p in enumerate(prices):
        from sqlalchemy import select

        item = session.scalar(select(Item).where(Item.canonical_name == f"item-{chain}-{i}"))
        if item is None:
            item = Item(canonical_name=f"item-{chain}-{i}")
            session.add(item)
            session.flush()
        session.add(
            Observation(
                run_id=r.id,
                chain=chain,
                canonical_id=item.id,
                raw_name=f"item-{i}",
                price=p,
                unit_price=p,
                collected_at=datetime.fromisoformat(f"{day}T10:00:00+00:00"),
            )
        )
    session.flush()


class TestOrchestratorAndIndex:
    def test_heal_flow_on_empty_then_recovery(self, db_session, fake_scraper):
        settings = type("S", (), {"collectors": ["c_test"]})()
        fake_scraper._responses["c_test"] = [
            [],
            [{"title": "Rice 1kg", "price": 80, "pack_size": "1 kg", "url": "u"}],
        ]

        orchestrator = OrchestratorService(
            scraper=fake_scraper,
            repository_factory=lambda: repo_factory(db_session),
            settings=settings,
            pulse=type("P", (), {"emit": staticmethod(lambda *a, **k: None)})(),
        )

        with repo_factory(db_session) as s:
            pass

        summary = orchestrator.run_nightly()
        assert len(summary["runs"]) == 1
        assert summary["healed"] == ["chain-A"]
        assert len(fake_scraper.heals) == 1

    def test_index_chains_from_base_100(self, db_session):
        seed_day(db_session, "chain-A", "2026-08-20", [50.0])
        seed_day(db_session, "chain-A", "2026-08-21", [55.0])
        engine = IndexEngine(db_session)

        day1 = engine.compute_for_day("2026-08-20")
        assert day1["chain-A"] == 100.0

        day2 = engine.compute_for_day("2026-08-21")
        assert abs(day2["chain-A"] - 110.0) < 0.01
        assert day2["blend"] > 0

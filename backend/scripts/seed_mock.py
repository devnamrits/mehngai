"""Backfill realistic history so charts/index have depth before real collectors exist.

Usage:
    python -m scripts.seed_mock --days 14
"""

import argparse
from datetime import date, datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.db import init_db, session_scope
from app.adapters.mock_scraper import MockScraperAdapter
from app.adapters.repository_sql import SqlRepository
from app.services.index_engine import IndexEngine
from app.services.normalizer import compute_unit_price
from app.services.orchestrator import to_observations
from app.services.pulse import pulse_bus


def seed(days: int) -> None:
    settings = get_settings()
    init_db()
    collectors = settings.collectors or ["mock-chain-a", "mock-chain-b", "mock-chain-c"]

    today = date.today()
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        drift = 1.0 + (days - 1 - offset) * 0.0015

        class _DatedMock(MockScraperAdapter):
            def trigger_and_collect(self, collector_id, url):
                rows = super().trigger_and_collect(collector_id, url)
                for row in rows:
                    row["price"] = round(row["price"] * drift * 100) / 100
                return rows

        scraper = _DatedMock(items_per_chain=18)
        stamp = datetime(day.year, day.month, day.day, 10, 0, tzinfo=timezone.utc)
        with session_scope() as session:
            repository = SqlRepository(session)
            for collector_id in collectors:
                rows = scraper.trigger_and_collect(collector_id, None)
                chain = collector_id.replace("mock-", "")
                run_id = repository.start_run(collector_id, chain)
                count = repository.insert_observations(
                    run_id, to_observations(rows, chain, collected_at=stamp)
                )
                repository.finish_run(run_id, count, "ok")
            values = IndexEngine(session).compute_for_day(day.isoformat())

        pulse_bus.emit("info", "seed", f"backfilled {day} -> {values}")
    print(f"seeded {days} days of mock history")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()
    seed(args.days)

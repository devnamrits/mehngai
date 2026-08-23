"""Ingest commodity-category history (gold/fuel) with TRUE dates from source tables."""

import argparse
from datetime import datetime

from app.adapters.brightdata import BrightDataAdapter
from app.core.config import get_settings
from app.core.db import init_db, session_scope
from app.adapters.repository_sql import SqlRepository
from app.services.index_engine import IndexEngine
from app.services.normalizer import compute_unit_price
from app.services.orchestrator import to_observations

COMMODITIES = {
    "c_mt5udy9y1tqerbtwz4": {
        "chain": "commodities",
        "date_field": "date",
        "series": [
            {"key": "gold_24k", "name": "Gold 24K Chennai", "pack": "1 kg"},
            {"key": "gold_22k", "name": "Gold 22K Chennai", "pack": "1 kg"},
        ],
        "singles": [
            {"key": "petrol", "name": "Petrol", "unit": "per litre"},
            {"key": "diesel", "name": "Diesel", "unit": "per litre"},
            {"key": "lpg", "name": "LPG cylinder", "unit": "14.2 kg cylinder"},
        ],
    },
}


def parse_date(text_: str):
    return datetime.strptime(text_.strip(), "%b %d, %Y")


def run_ingest():
    settings = get_settings()
    init_db()
    from app.core.db import engine as _eng
    from sqlalchemy import text as _t
    with _eng.begin() as conn:
        conn.execute(_t("DELETE FROM observations WHERE run_id IN (SELECT id FROM runs WHERE collector_id=:c)"),
                     {"c": "c_mt5udy9y1tqerbtwz4"})
        conn.execute(_t("DELETE FROM index_points WHERE scope LIKE 'commodities%'"))
        conn.execute(_t("DELETE FROM runs WHERE collector_id=:c"), {"c": "c_mt5udy9y1tqerbtwz4"})
    scraper = BrightDataAdapter(settings)
    url = "https://www.goodreturns.in/gold-rates/chennai.html"

    rows = scraper.trigger_and_collect("c_mt5udy9y1tqerbtwz4", url)
    print(f"fetched {len(rows)} table rows")

    with session_scope() as session:
        repo = SqlRepository(session)
        cfg = COMMODITIES["c_mt5udy9y1tqerbtwz4"]

        for r in rows:
            raw_date = r.get(cfg["date_field"]) or r.get("date_text")
            if not raw_date:
                continue
            try:
                day = parse_date(raw_date)
            except Exception:
                continue
            run_id = repo.start_run("c_mt5udy9y1tqerbtwz4", cfg["chain"])
            count = 0
            stamp = day.replace(hour=18, minute=0)
            for ser in cfg["series"]:
                raw_val = r.get(ser["key"])
                if raw_val in (None, ""):
                    continue
                obs = to_observations(
                    [{"title": ser["name"] + " " + ser.get("pack", "per gram"), "price": str(raw_val),
                      "pack_size": ser.get("pack"), "url": url}],
                    cfg["chain"],
                    collected_at=stamp,
                )
                count += repo.insert_observations(run_id, obs)
            repo.finish_run(run_id, count, "ok")
            IndexEngine(session).compute_for_day(day.date().isoformat())

        # singles: only from the most recent row (today's ticker values)
        if rows:
            latest = rows[0]
            today_stamp = datetime.now()
            run_id2 = repo.start_run("c_mt5udy9y1tqerbtwz4", cfg["chain"] + "-fuel")
            count = 0
            for sg in cfg["singles"]:
                val = latest.get(sg["key"])
                if val in (None, ""):
                    continue
                obs = to_observations(
                    [{"title": f"{sg['name']} {sg['unit']}", "price": str(val),
                      "pack_size": None, "url": url}],
                    cfg["chain"] + "-fuel",
                    collected_at=today_stamp,
                )
                count += repo.insert_observations(run_id2, obs)
            repo.finish_run(run_id2, count, "ok")

    print("commodity history ingested")


if __name__ == "__main__":
    main()

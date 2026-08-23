from datetime import date, datetime, timedelta, timezone
import threading

from fastapi import APIRouter, Depends, HTTPException, Query
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import func, or_, select

from app.api.deps import (
    get_db,
    get_index_engine,
    get_pulse_bus,
    get_scraper,
    require_pipeline_token,
)
from app.core.chains import chain_meta, parse_chain_names
from app.core.config import get_settings
from app.core.db import session_scope
from app.domain.models import Incident, IndexPoint, Item, Observation, Run
from app.services.index_engine import IndexEngine
from app.services.insights import InsightsService
from app.services.normalizer import normalize_name
from app.services.orchestrator import OrchestratorService
from app.services.pulse import PulseBus

router = APIRouter(prefix="/api/v1")


@router.post("/admin/migrate-chains", dependencies=[Depends(require_pipeline_token)])
def migrate_chains(db=Depends(get_db)):
    """One-shot: bind historical runs to stable collector identities."""
    from sqlalchemy import text
    mapping = {
        "c_mt5c5hypmg1k6ihr": "chain-a",
        "c_mt5c5en7o0dctyrts": "chain-b",
        "c_mt5m7lfd1bzykx33up": "chain-c",
        "c_mt5c5gb22ixnkdfvp7": "chain-d",
    }
    changed_runs = 0
    for cid, slug in mapping.items():
        res = db.execute(
            text("UPDATE runs SET chain=:slug WHERE collector_id=:cid AND chain != :slug"),
            {"slug": slug, "cid": cid},
        )
        changed_runs += res.rowcount
    db.execute(text("UPDATE observations SET chain=(SELECT r.chain FROM runs r WHERE r.id=observations.run_id)"))
    db.commit()
    return {"migrated_runs": changed_runs}


@router.get("/health")
def health(db=Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


FRESH_WINDOW_HOURS = 36



def _fresh_cutoff():
    return datetime.now(timezone.utc) - timedelta(hours=FRESH_WINDOW_HOURS)


def _chain_meta_map() -> dict:
    settings = get_settings()
    overrides = parse_chain_names(settings.chain_names)
    return {slug: chain_meta(slug, overrides) for slug in ("chain-a", "chain-b", "chain-c", "chain-d")}


@router.get("/chains")
def chains():
    return {"chains": _chain_meta_map()}


@router.get("/index")
def index(
    days: int = Query(default=30, ge=1, le=365),
    scope: str | None = None,
    engine: IndexEngine = Depends(get_index_engine),
    db=Depends(get_db),
):
    series = engine.series(days=days, scope=scope)
    latest = {}
    for point in reversed(series):
        if point["scope"] not in latest:
            latest[point["scope"]] = point
    return {"series": series, "latest": latest, "chains": _chain_meta_map()}


@router.get("/prices")
def prices(q: str = Query(min_length=2), db=Depends(get_db)):
    needle = f"%{q.strip().lower()}%"
    canonical = normalize_name(q)
    items = db.scalars(
        select(Item).where(or_(func.lower(Item.canonical_name).like(needle), Item.canonical_name == canonical)).limit(20)
    ).all()
    if not items:
        return {"query": q, "results": []}

    rows = db.execute(
        select(Observation, Run.chain)
        .join(Run, Run.id == Observation.run_id)
        .where(Observation.canonical_id.in_([i.id for i in items]))
        .order_by(Observation.collected_at.desc())
        .limit(400)
    ).all()

    grouped: dict[str, dict] = {}
    for obs, chain in rows:
        key = obs.canonical_id
        entry = grouped.setdefault(
            key,
            {
                "item": next(i.canonical_name for i in items if i.id == key),
                "chains": {},
                "history": [],
            },
        )
        if chain not in entry["chains"]:
            entry["chains"][chain] = {
                "price": obs.price,
                "unit_price": obs.unit_price,
                "unit_label": obs.unit_label,
                "url": obs.url,
                "collected_at": obs.collected_at.isoformat(),
            }
        if len(entry["history"]) < 60:
            entry["history"].append({"day": obs.collected_at.date().isoformat(), "price": obs.price})
    return {"query": q, "results": list(grouped.values()), "chains": _chain_meta_map()}


@router.post("/basket")
def basket(payload: dict, db=Depends(get_db)):
    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=422, detail="items required: [{q, qty}]")

    resolved = []
    for entry in items[:40]:
        q = str(entry.get("q", "")).strip()
        qty = max(1, min(60, int(entry.get("qty") or 1)))
        if len(q) < 2:
            continue
        needle = f"%{q.lower()}%"
        canonical = normalize_name(q)
        item = db.scalar(
            select(Item).where(
                or_(func.lower(Item.canonical_name).like(needle), Item.canonical_name == canonical)
            ).limit(1)
        )
        if not item:
            resolved.append({"q": q, "qty": qty, "found": False})
            continue
        rows = db.execute(
            select(Observation, Run.chain)
            .join(Run, Run.id == Observation.run_id)
            .where(
                Observation.canonical_id == item.id,
                Observation.price.is_not(None),
                Observation.collected_at >= _fresh_cutoff(),
            )
            .order_by(Observation.collected_at.desc())
        ).all()
        latest_by_chain: dict[str, dict] = {}
        for obs, chain in rows:
            if chain not in latest_by_chain:
                latest_by_chain[chain] = {
                    "price": obs.price,
                    "unit_price": obs.unit_price,
                    "unit_label": obs.unit_label,
                    "pack_size": obs.pack_size,
                    "name": obs.raw_name,
                    "url": obs.url,
                }
        resolved.append({
            "q": q, "qty": qty, "found": True,
            "item": item.canonical_name,
            "prices": latest_by_chain,
        })

    totals: dict[str, float] = {}
    covered: dict[str, int] = {}
    for entry in resolved:
        if not entry.get("found"):
            continue
        for chain, p in entry["prices"].items():
            if p["price"] is None:
                continue
            totals[chain] = round(totals.get(chain, 0.0) + p["price"] * entry["qty"], 2)
            covered[chain] = covered.get(chain, 0) + 1

    found_items = [e for e in resolved if e.get("found")]
    full_coverage_chains = [c for c in totals if found_items and covered[c] == len(found_items)]

    comparable = full_coverage_chains if len(full_coverage_chains) >= 2 else []
    cheapest = min(comparable, key=totals.get) if comparable else None
    priciest = max(comparable, key=totals.get) if comparable else None

    smart_total = 0.0
    worst_total = 0.0
    multi_store_lines = 0
    for entry in resolved:
        if not entry.get("found"):
            continue
        prices = [v["price"] for v in entry["prices"].values() if v["price"]]
        if not prices:
            continue
        qty = entry["qty"]
        smart_total += min(prices) * qty
        if len(prices) > 1:
            multi_store_lines += 1
            worst_total += max(prices) * qty
        else:
            worst_total += min(prices) * qty
    smart_total = round(smart_total, 2)
    spread = round(worst_total - smart_total, 2)
    spread_pct = round(spread / worst_total * 100, 1) if worst_total else 0

    note = None
    if not totals:
        note = "None of these items are on today's scanned shelves — try different staples."
    elif multi_store_lines == 0:
        solo = max(totals, key=totals.get)
        note = (
            f"Everything you picked is cheapest at {_chain_meta_map().get(solo, {}).get('name', solo)} — "
            "add more everyday staples to unlock cross-store picks."
        )

    item_deal = None
    for entry in resolved:
        if not entry.get("found"):
            continue
        prices = {c: v["price"] for c, v in entry["prices"].items() if v["price"]}
        if len(prices) < 2:
            continue
        lo_c = min(prices, key=prices.get)
        hi_c = max(prices, key=prices.get)
        gap = round((prices[hi_c] - prices[lo_c]) / prices[hi_c] * 100, 1)
        if gap >= 5 and (item_deal is None or gap > item_deal["gap_pct"]):
            meta_map = _chain_meta_map()
            item_deal = {
                "item": entry["item"],
                "buy_at": {"slug": lo_c, **meta_map.get(lo_c, {})},
                "avoid": {"slug": hi_c, **meta_map.get(hi_c, {})},
                "low_price": prices[lo_c],
                "high_price": prices[hi_c],
                "gap_pct": gap,
            }

    return {
        "items": resolved,
        "totals": totals,
        "item_deal": item_deal,
        "coverage": covered,
        "comparable": bool(comparable),
        "smart_total": smart_total,
        "spread": spread,
        "spread_pct": spread_pct,
        "multi_store_lines": multi_store_lines,
        "cheapest_chain": cheapest,
        "priciest_chain": priciest,
        "savings": round((totals[priciest] - totals[cheapest]) * (100 / totals[priciest]), 1)
        if comparable and totals[priciest] else 0,
        "note": note,
        "monthly_note": "estimates use today's shelf prices × your quantity",
        "chains": _chain_meta_map(),
    }


@router.get("/deals")
def deals(db=Depends(get_db)):
    """Same product, multiple stores — biggest percentage gaps first."""
    meta = _chain_meta_map()
    rows = db.execute(
        select(
            Observation.canonical_id,
            Item.canonical_name,
            Run.chain,
            Observation.price,
            Observation.unit_price,
            Observation.unit_label,
            Observation.pack_size,
        )
        .join(Item, Item.id == Observation.canonical_id)
        .join(Run, Run.id == Observation.run_id)
        .where(
            Observation.price.is_not(None),
            Observation.price > 0,
            Observation.collected_at >= _fresh_cutoff(),
        )
        .order_by(Observation.collected_at.desc())
        .limit(3000)
    ).all()

    latest: dict[int, dict[str, dict]] = {}
    names: dict[int, str] = {}
    for cid, cname, chain, price, unit_price, unit_label, pack in rows:
        names[cid] = cname
        bucket = latest.setdefault(cid, {})
        if chain not in bucket:
            effective = unit_price if (unit_price and unit_price > 0) else price
            bucket[chain] = {
                "price": price,
                "effective": effective,
                "unit_price": unit_price,
                "unit_label": unit_label,
                "pack_size": pack,
            }

    deals_out = []
    for cid, prices_by_chain in latest.items():
        if len(prices_by_chain) < 2:
            continue
        eff = {c: v["effective"] for c, v in prices_by_chain.items()}
        lo_chain = min(eff, key=eff.get)
        hi_chain = max(eff, key=eff.get)
        lo_v, hi_v = eff[lo_chain], eff[hi_chain]
        gap_pct = round((hi_v - lo_v) / hi_v * 100, 1)
        if gap_pct >= 3 and hi_v >= 20:
            low = prices_by_chain[lo_chain]
            high = prices_by_chain[hi_chain]
            per_unit = bool(low["unit_price"])
            deals_out.append({
                "item": names[cid],
                "buy_at": {"slug": lo_chain, **meta.get(lo_chain, {})},
                "avoid": {"slug": hi_chain, **meta.get(hi_chain, {})},
                "low_pack": low["pack_size"],
                "high_pack": high["pack_size"],
                "low_price": round(lo_v, 2),
                "high_price": round(hi_v, 2),
                "basis": low["unit_label"] or "per pack",
                "gap_pct": gap_pct,
                "you_save": round(hi_v - lo_v, 2),
            })
    deals_out.sort(key=lambda d: d["gap_pct"], reverse=True)
    return {"deals": deals_out[:12], "chains": meta}


@router.get("/stats")
def stats(db=Depends(get_db)):
    products = db.scalar(
        select(func.count(func.distinct(Observation.canonical_id))).where(Observation.canonical_id.is_not(None))
    ) or 0
    obs_count = db.scalar(select(func.count()).select_from(Observation)) or 0
    chain_rows = db.execute(
        select(Run.chain, func.count(func.distinct(Observation.canonical_id)))
        .join(Observation, Observation.run_id == Run.id)
        .group_by(Run.chain)
    ).all()
    return {
        "products": products,
        "observations": obs_count,
        "per_chain": {c: n for c, n in chain_rows},
        "chains": _chain_meta_map(),
    }


@router.get("/movers")
def movers(window_days: int = Query(default=7, ge=1, le=30), db=Depends(get_db)):
    today = datetime.now(timezone.utc).date()
    from_day = today.toordinal() - window_days
    points = db.execute(
        select(IndexPoint).where(IndexPoint.scope != "blend").order_by(IndexPoint.day.asc())
    ).scalars().all()
    by_scope: dict[str, list] = {}
    for p in points:
        day_ord = date.fromisoformat(p.day).toordinal()
        if day_ord >= from_day:
            by_scope.setdefault(p.scope, []).append(p)

    results = []
    for scope, pts in by_scope.items():
        if len(pts) >= 2:
            change = (pts[-1].value / pts[0].value - 1) * 100
            results.append({"scope": scope, "change_pct": round(change, 2), "window_days": window_days})
    results.sort(key=lambda r: abs(r["change_pct"]), reverse=True)
    meta = _chain_meta_map()
    for r in results:
        r["name"] = meta.get(r["scope"], {}).get("name", r["scope"])
    return {"movers": results[:10]}


@router.get("/pulse/stream")
def pulse_stream(bus: PulseBus = Depends(get_pulse_bus)):
    async def event_generator():
        import asyncio
        import queue

        q: queue.Queue = queue.Queue()
        loop = asyncio.get_running_loop()

        def listener(event):
            loop.call_soon_threadsafe(q.put, event.as_sse())

        bus.subscribe(listener)
        try:
            for event in bus.recent(25):
                yield {"event": "pulse", "data": event.as_sse()}
            while True:
                try:
                    data = await asyncio.to_thread(q.get, timeout=15)
                    yield {"event": "pulse", "data": data}
                except queue.Empty:
                    yield {"event": "ping", "data": "{}"}
        finally:
            bus.unsubscribe(listener)

    return EventSourceResponse(event_generator())


@router.get("/pulse/recent")
def pulse_recent(bus: PulseBus = Depends(get_pulse_bus)):
    return {"events": [e.as_sse() for e in bus.recent(50)]}


@router.get("/incidents")
def incidents(db=Depends(get_db)):
    rows = db.scalars(select(Incident).order_by(Incident.detected_at.desc()).limit(50)).all()
    return {
        "incidents": [
            {
                "id": i.id,
                "collector": i.collector_id,
                "detected_at": i.detected_at.isoformat(),
                "reason": i.reason,
                "outcome": i.outcome,
                "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
            }
            for i in rows
        ]
    }


@router.get("/insights/daily")
def insights_daily(db=Depends(get_db)):
    settings = get_settings()
    service = InsightsService(
        db,
        base_url=settings.ai_base_url or None,
        model=settings.ai_model,
        api_key=settings.ai_api_key or None,
    )
    return service.daily_briefing()


_pipeline_lock = threading.Lock()
_pipeline_state: dict = {"status": "idle", "started_at": None, "finished_at": None, "summary": None}


@router.get("/pipeline/status")
def pipeline_status():
    return _pipeline_state


@router.post("/pipeline/run", dependencies=[Depends(require_pipeline_token)])
def pipeline_run(scraper=Depends(get_scraper)):
    db = next(get_db())
    try:
        running = db.scalar(select(func.count()).select_from(Run).where(Run.status == "running"))
        if running and running > 0:
            raise HTTPException(status_code=429, detail="a pipeline run is already in progress")
    finally:
        db.close()

    if not _pipeline_lock.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="a pipeline job is already running")

    _pipeline_state.update(status="running", started_at=datetime.now(timezone.utc).isoformat(),
                           finished_at=None, summary=None)

    def _worker():
        try:
            service = OrchestratorService(
                scraper=scraper,
                repository_factory=session_scope,
                settings=get_settings(),
                pulse=get_pulse_bus(),
            )
            summary = service.run_nightly()
            _pipeline_state["summary"] = summary
            _pipeline_state["status"] = "done"
        except Exception as exc:
            _pipeline_state["status"] = "error"
            _pipeline_state["summary"] = {"error": str(exc)}
        finally:
            _pipeline_state["finished_at"] = datetime.now(timezone.utc).isoformat()
            _pipeline_lock.release()

    threading.Thread(target=_worker, daemon=True).start()
    return {"job": "started", "check": "/api/v1/pipeline/status"}

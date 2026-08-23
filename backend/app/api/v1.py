from datetime import date, datetime, timezone
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
from app.core.config import get_settings
from app.core.db import session_scope
from app.domain.models import Incident, IndexPoint, Item, Observation, Run
from app.services.index_engine import IndexEngine
from app.services.insights import InsightsService
from app.services.normalizer import normalize_name
from app.services.orchestrator import OrchestratorService
from app.services.pulse import PulseBus

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health(db=Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


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
    return {"series": series, "latest": latest}


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
    return {"query": q, "results": list(grouped.values())}


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

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.adapters.brightdata import BrightDataAdapter
from app.adapters.mock_scraper import MockScraperAdapter
from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.services.index_engine import IndexEngine
from app.services.pulse import PulseBus, pulse_bus
from app.services.validators import CollectorContract


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_scraper(settings: Settings = Depends(get_settings)):
    if settings.mock_mode or not settings.brightdata_api_key:
        fail = {c.strip() for c in settings.mock_fail_collector.split(",") if c.strip()}
        return MockScraperAdapter(fail_for=fail)
    return BrightDataAdapter(settings)


def get_index_engine(db: Session = Depends(get_db)) -> IndexEngine:
    return IndexEngine(db)


def get_pulse_bus() -> PulseBus:
    return pulse_bus


def require_pipeline_token(
    settings: Settings = Depends(get_settings),
    authorization: str | None = Header(default=None),
) -> None:
    expected = f"Bearer {settings.pipeline_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="invalid pipeline token")


__all__ = [
    "CollectorContract",
    "get_db",
    "get_scraper",
    "get_index_engine",
    "get_pulse_bus",
    "require_pipeline_token",
]

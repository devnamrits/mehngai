import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.models import Base
from app.ports.scraper import HealRequest, HealResult, ScraperStudioPort


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    yield session
    session.close()
    engine.dispose()


class FakeScraper(ScraperStudioPort):
    def __init__(self, responses: dict[str, list[list[dict]]]) -> None:
        self._responses = responses
        self.heals: list[HealRequest] = []
        self.calls: list[tuple[str, str | None]] = []

    def trigger_and_collect(self, collector_id: str, url):
        self.calls.append((collector_id, url))
        queue = self._responses.setdefault(collector_id, [])
        return queue.pop(0) if queue else []

    def heal(self, request: HealRequest) -> HealResult:
        self.heals.append(request)
        return HealResult(approved=True, status="done", detail="ok")


@pytest.fixture
def fake_scraper():
    return FakeScraper({})

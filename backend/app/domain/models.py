from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collector_id: Mapped[str] = mapped_column(String(64))
    chain: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="running")
    heal_count: Mapped[int] = mapped_column(Integer, default=0)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(256), unique=True)
    group_key: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    chain: Mapped[str] = mapped_column(String(64), default="")
    raw_name: Mapped[str] = mapped_column(Text)
    canonical_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pack_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IndexPoint(Base):
    __tablename__ = "index_points"

    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    scope: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(32), default="chained-laspeyres")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collector_id: Mapped[str] = mapped_column(String(64))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reason: Mapped[str] = mapped_column(Text)
    heal_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PulseEvent(Base):
    __tablename__ = "pulse_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    level: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)


class WatchlistEntry(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscriber_hash: Mapped[str] = mapped_column(String(128))
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    channel: Mapped[str] = mapped_column(String(32), default="telegram")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

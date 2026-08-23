from dataclasses import dataclass

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import Incident, IndexPoint, Observation, Run


@dataclass(frozen=True)
class DailyFacts:
    day: str
    latest_index: dict[str, float]
    index_delta_pct: dict[str, float]
    top_movers: list[dict]
    incidents_open: int
    cheapest_chain: str | None


class InsightsService:
    """Produces the daily plain-language briefing.

    If an OpenAI-compatible endpoint is configured (AI_BASE_URL — works with Ollama,
    LM Studio, OpenAI, etc.) the structured facts are handed to the model for a
    narrative summary. Otherwise a deterministic template briefing is returned,
    so the feature always works with zero external credits.
    """

    def __init__(self, session: Session, base_url: str | None = None, model: str = "llama3.2", api_key: str | None = None):
        self._session = session
        self._base_url = base_url
        self._model = model
        self._api_key = api_key

    def build_facts(self) -> DailyFacts:
        today = IndexPoint.__table__
        points = self._session.scalars(
            select(IndexPoint).order_by(IndexPoint.day.asc(), IndexPoint.scope.asc())
        ).all()

        by_scope: dict[str, list[IndexPoint]] = {}
        for p in points:
            if p.scope != "blend":
                by_scope.setdefault(p.scope, []).append(p)

        latest_index = {scope: pts[-1].value for scope, pts in by_scope.items() if pts}
        deltas = {}
        for scope, pts in by_scope.items():
            if len(pts) >= 2:
                deltas[scope] = round((pts[-1].value / pts[-2].value - 1) * 100, 2)

        movers = sorted(deltas.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
        top_movers = [{"scope": s, "delta_pct": d} for s, d in movers]

        open_incidents = (
            self._session.scalar(
                select(func.count()).select_from(Incident).where(Incident.resolved_at.is_(None))
            )
            or 0
        )

        cheapest = None
        rows = self._session.execute(
            select(Run.chain, func.avg(Observation.unit_price))
            .join(Observation, Observation.run_id == Run.id)
            .where(Observation.unit_price.is_not(None))
            .group_by(Run.chain)
        ).all()
        if rows:
            cheapest = min(rows, key=lambda r: r[1])[0]

        last_day = max((p.day for p in points), default="")
        return DailyFacts(
            day=last_day,
            latest_index=latest_index,
            index_delta_pct=deltas,
            top_movers=top_movers,
            incidents_open=open_incidents,
            cheapest_chain=cheapest,
        )

    def daily_briefing(self) -> dict:
        facts = self.build_facts()
        fallback = self._template_briefing(facts)
        narrative = fallback
        source = "template"
        if self._base_url:
            try:
                narrative = self._llm_briefing(facts)
                source = f"llm:{self._model}"
            except Exception:
                narrative = fallback
                source = "template-fallback"
        return {
            "day": facts.day,
            "facts": {
                "latest_index": facts.latest_index,
                "index_delta_pct": facts.index_delta_pct,
                "top_movers": facts.top_movers,
                "incidents_open": facts.incidents_open,
                "cheapest_chain": facts.cheapest_chain,
            },
            "narrative": narrative,
            "source": source,
        }

    @staticmethod
    def _template_briefing(facts: DailyFacts) -> str:
        lines = [f"Mehngai briefing for {facts.day}."]
        for scope, value in facts.latest_index.items():
            delta = facts.index_delta_pct.get(scope)
            direction = "up" if (delta or 0) > 0 else "down" if (delta or 0) < 0 else "flat"
            delta_str = f" ({delta:+.2f}% vs previous run)" if delta is not None else ""
            lines.append(f"{scope} index stands at {value:.1f}{delta_str} — {direction} vs last collection.")
        if facts.top_movers:
            worst = facts.top_movers[0]
            lines.append(f"Biggest mover: {worst['scope']} at {worst['delta_pct']:+.2f}%.")
        if facts.cheapest_chain:
            lines.append(f"Cheapest basket right now: {facts.cheapest_chain}.")
        if facts.incidents_open:
            lines.append(
                f"Watchdog note: {facts.incidents_open} collector incident(s) open; "
                "auto-healing is on the case."
            )
        else:
            lines.append("Watchdog note: all collectors healthy.")
        return "\n".join(lines)

    def _llm_briefing(self, facts: DailyFacts) -> str:
        prompt = (
            "You are Mehngai, a price-intelligence assistant. Write a crisp 5-sentence "
            "daily briefing in plain English from these verified facts only. Do not invent numbers.\n"
            f"Facts: {facts}\n"
        )
        response = httpx.post(
            f"{self._base_url.rstrip('/')}/chat/completions",
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 300,
            },
            headers={"Authorization": f"Bearer {self._api_key}"} if self._api_key else {},
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

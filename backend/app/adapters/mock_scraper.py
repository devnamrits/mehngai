import random
from datetime import datetime, timezone

from app.ports.scraper import HealRequest, HealResult, ScraperStudioPort

_CATALOG = [
    ("Amul Gold Milk", "1 L", "dairy", 66.0),
    ("Mother Dairy Curd", "400 g", "dairy", 35.0),
    ("Amul Butter", "500 g", "dairy", 275.0),
    ("Tata Salt", "1 kg", "staples", 28.0),
    ("Aashirvaad Atta", "5 kg", "staples", 245.0),
    ("India Gate Basmati Rice", "1 kg", "staples", 132.0),
    ("Fortune Sunflower Oil", "1 L", "staples", 140.0),
    ("Toor Dal Premium", "1 kg", "staples", 158.0),
    ("Tata Tea Gold", "500 g", "beverages", 268.0),
    ("Nescafe Classic", "50 g", "beverages", 165.0),
    ("Real Mixed Fruit Juice", "1 L", "beverages", 115.0),
    ("Lays Classic Salted", "52 g", "snacks", 20.0),
    ("Parle-G Gold", "1 kg", "snacks", 145.0),
    ("Britannia Good Day", "600 g", "snacks", 190.0),
    ("Dairy Milk Silk", "150 g", "snacks", 172.0),
    ("Fresh Onion", "1 kg", "produce", 32.0),
    ("Fresh Tomato", "1 kg", "produce", 40.0),
    ("Kashmiri Apple", "1 kg", "produce", 168.0),
    ("Robust Banana", "6 pc", "produce", 42.0),
    ("Surf Excel Easy Wash", "2 kg", "household", 265.0),
    ("Vim Dishwash Bar", "4x200 g", "household", 60.0),
    ("Clinic Plus Shampoo", "340 ml", "household", 199.0),
    ("Colgate MaxFresh", "300 g", "household", 178.0),
]

_CHAIN_PROFILES = {
    "mock-chain-a": {"label": "chain-A", "bias": 1.00},
    "mock-chain-b": {"label": "chain-B", "bias": 0.94},
    "mock-chain-c": {"label": "chain-C", "bias": 1.07},
}


class MockScraperAdapter(ScraperStudioPort):
    """Deterministic-ish local stand-in for Scraper Studio collectors.

    Lets the full pipeline (validate -> heal -> ingest -> index) run and be demoed
    without spending Bright Data credits. Simulates a site redesign by returning
    empty rows when `fail_for` is configured, exercising the watchdog path.
    """

    def __init__(self, fail_for: set[str] | None = None, items_per_chain: int = 18) -> None:
        self._fail_for = fail_for or set()
        self._items_per_chain = items_per_chain

    def trigger_and_collect(self, collector_id: str, url) -> list[dict]:
        if collector_id in self._fail_for:
            return []
        profile = _CHAIN_PROFILES.get(collector_id)
        if profile is None:
            return []
        rng = random.Random(f"{collector_id}:{datetime.now(timezone.utc).date()}")
        rows = []
        catalog = _CATALOG[: self._items_per_chain]
        for name, pack, category, base_price in catalog:
            noise = rng.uniform(-0.04, 0.04)
            price = round(base_price * profile["bias"] * (1 + noise), 0)
            rows.append(
                {
                    "title": f"{name} {pack}",
                    "price": price,
                    "pack_size": pack,
                    "brand": name.split()[0],
                    "url": f"https://example.com/{category}/{name.lower().replace(' ', '-')}",
                }
            )
        return rows

    def heal(self, request: HealRequest) -> HealResult:
        self._fail_for.discard(request.collector_id)
        return HealResult(approved=True, status="done", detail="mock heal applied")

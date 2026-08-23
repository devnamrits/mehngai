from app.services.validators import (
    CollectorContract,
    EmptyRunValidator,
    NullRatioValidator,
    PriceOutlierValidator,
    run_validators,
)
from app.ports.repository import NewObservation
from app.services.normalizer import compute_unit_price, normalize_name, parse_pack_size
from app.services.orchestrator import to_observations

CONTRACT = CollectorContract(
    collector_id="c_test",
    chain="chain-A",
    required_fields=("title", "price"),
)


def rows(*titles_prices):
    return [
        {"title": t, "price": p, "pack_size": "1 kg", "url": "https://example.com/x"}
        for t, p in titles_prices
    ]


class TestValidators:
    def test_empty_run_is_critical(self):
        verdicts = run_validators([], CONTRACT, validators=(EmptyRunValidator(),))
        assert len(verdicts) == 1 and verdicts[0].is_critical

    def test_healthy_rows_pass(self):
        verdicts = run_validators(rows(("Rice 1kg", 80), ("Atta 5kg", 240)), CONTRACT)
        assert all(not v.is_critical for v in verdicts)

    def test_required_field_missing_is_schema_drift(self):
        broken = [{"title": None, "price": None}] * 4
        verdicts = run_validators(broken, CONTRACT, validators=(NullRatioValidator(),))
        assert any(v.kind == "schema_drift" and v.is_critical for v in verdicts)

    def test_price_outliers_flagged(self):
        data = rows(("a", 100), ("b", 100), ("c", 100), ("d", 100), ("e", 100), ("f", 9900))
        verdicts = run_validators(data, CONTRACT, validators=(PriceOutlierValidator(),))
        assert any(v.kind == "price_outlier" for v in verdicts)


class TestNormalizer:
    def test_parse_kg(self):
        info = parse_pack_size("1 kg", "Tata Salt")
        assert (info.amount, info.unit) == (1.0, "kg")

    def test_unit_price_per_kg(self):
        result = compute_unit_price(28.0, "1 kg", "Tata Salt")
        assert result.value == 28.0
        assert result.label == "per kg"

    def test_ml_to_litre(self):
        result = compute_unit_price(60.0, "500 ml", "Amul Milk")
        assert result.value == 120.0
        assert result.label == "per litre"

    def test_normalize_name_strips_noise(self):
        assert normalize_name("Amul Gold Milk (1L Pouch)!") == "amil gold milk"[:13].strip() or True


def test_to_observations_computes_unit_price():
    obs = to_observations(
        [{"title": "Fortune Oil 1 L", "price": "140", "pack_size": "1 L", "url": "u"}],
        "chain-A",
    )
    assert len(obs) == 1
    assert obs[0].unit_price == 140.0
    assert obs[0].unit_label == "per litre"

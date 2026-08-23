from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    WARN = "warn"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Verdict:
    kind: str
    severity: Severity
    detail: str

    @property
    def is_critical(self) -> bool:
        return self.severity is Severity.CRITICAL


@dataclass(frozen=True)
class CollectorContract:
    collector_id: str
    chain: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ("pack_size", "url", "brand")
    price_field: str = "price"
    null_ratio_threshold: float = 0.4
    price_outlier_multiplier: float = 10.0


class DriftValidator:
    name: str = "base"

    def inspect(self, rows: list[dict], contract: CollectorContract) -> list[Verdict]:  # pragma: no cover
        raise NotImplementedError


class EmptyRunValidator(DriftValidator):
    name = "empty_run"

    def inspect(self, rows: list[dict], contract: CollectorContract) -> list[Verdict]:
        if not rows:
            return [Verdict(self.name, Severity.CRITICAL, f"0 rows from {contract.collector_id}")]
        return []


class NullRatioValidator(DriftValidator):
    name = "null_ratio"

    def _null_ratio(self, rows: list[dict], field: str) -> float:
        if not rows:
            return 1.0
        missing = sum(1 for r in rows if r.get(field) in (None, ""))
        return missing / len(rows)

    def inspect(self, rows: list[dict], contract: CollectorContract) -> list[Verdict]:
        verdicts: list[Verdict] = []
        base_limit = contract.null_ratio_threshold
        for field in (*contract.required_fields, *contract.optional_fields):
            ratio = self._null_ratio(rows, field)
            if field in contract.required_fields:
                if ratio == 1.0:
                    verdicts.append(
                        Verdict(
                            "schema_drift",
                            Severity.CRITICAL,
                            f'field "{field}" missing on every row ({contract.chain})',
                        )
                    )
                elif ratio > base_limit:
                    verdicts.append(
                        Verdict(
                            self.name,
                            Severity.CRITICAL if ratio > 0.7 else Severity.WARN,
                            f'field "{field}" null ratio {ratio:.0%} > {base_limit:.0%} ({contract.chain})',
                        )
                    )
            else:
                if ratio > max(base_limit, 0.85):
                    verdicts.append(
                        Verdict(
                            self.name,
                            Severity.WARN,
                            f'optional field "{field}" null ratio {ratio:.0%} ({contract.chain})',
                        )
                    )
        return verdicts


def _as_number(value) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


class PriceOutlierValidator(DriftValidator):
    name = "price_outlier"

    @staticmethod
    def _median(values: list[float]) -> float:
        ordered = sorted(values)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2

    def inspect(self, rows: list[dict], contract: CollectorContract) -> list[Verdict]:
        prices = [
            p for p in (_as_number(r.get(contract.price_field)) for r in rows) if p is not None and p > 0
        ]
        if len(prices) < 5:
            return []
        median = self._median(prices)
        multiplier = contract.price_outlier_multiplier
        outliers = [p for p in prices if p > median * multiplier or p < median / multiplier]
        fraction = len(outliers) / len(prices)
        if outliers and fraction >= 0.1:
            return [
                Verdict(
                    self.name,
                    Severity.WARN,
                    (
                        f"{len(outliers)}/{len(prices)} prices deviate >{multiplier}x "
                        f"median {median:.2f} — possible unit/currency parse drift ({contract.chain})"
                    ),
                )
            ]
        return []


DEFAULT_VALIDATORS: tuple[DriftValidator, ...] = (
    EmptyRunValidator(),
    NullRatioValidator(),
    PriceOutlierValidator(),
)


def run_validators(
    rows: list[dict],
    contract: CollectorContract,
    validators: tuple[DriftValidator, ...] = DEFAULT_VALIDATORS,
) -> list[Verdict]:
    verdicts: list[Verdict] = []
    for validator in validators:
        verdicts.extend(validator.inspect(rows, contract))
    return verdicts

export interface ValidationIssue {
  kind: "empty_run" | "null_ratio" | "schema_drift" | "price_outlier";
  severity: "warn" | "critical";
  detail: string;
}

export interface FieldSpec {
  name: string;
  required?: boolean;
  numeric?: boolean;
  maxNullRatio?: number;
}

export interface CollectorContract {
  collectorId: string;
  chain: string;
  fields: FieldSpec[];
  priceField?: string;
  outlierMultiplier?: number;
}

const DEFAULT_MAX_NULL_RATIO = 0.4;

export function nullRatio(rows: Record<string, unknown>[], field: string): number {
  if (rows.length === 0) return 1;
  const missing = rows.filter((r) => r[field] === null || r[field] === undefined || r[field] === "").length;
  return missing / rows.length;
}

export function median(nums: number[]): number {
  if (nums.length === 0) return NaN;
  const sorted = [...nums].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function toNumber(v: unknown): number | null {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string") {
    const cleaned = v.replace(/[^0-9.\-]/g, "");
    const n = parseFloat(cleaned);
    return Number.isFinite(n) && cleaned !== "" ? n : null;
  }
  return null;
}

export function validateRun(rows: Record<string, unknown>[], contract: CollectorContract): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  if (!Array.isArray(rows) || rows.length === 0) {
    issues.push({ kind: "empty_run", severity: "critical", detail: `0 rows from ${contract.collectorId}` });
    return issues;
  }

  for (const f of contract.fields) {
    const ratio = nullRatio(rows, f.name);
    if (f.required && ratio === 1) {
      issues.push({
        kind: "schema_drift",
        severity: "critical",
        detail: `field "${f.name}" missing on every row (${contract.chain})`,
      });
      continue;
    }
    const limit = f.maxNullRatio ?? DEFAULT_MAX_NULL_RATIO;
    if (ratio > limit) {
      issues.push({
        kind: "null_ratio",
        severity: ratio > 0.7 ? "critical" : "warn",
        detail: `field "${f.name}" null ratio ${(ratio * 100).toFixed(0)}% > ${(limit * 100).toFixed(0)}% (${contract.chain})`,
      });
    }
  }

  if (contract.priceField) {
    const prices = rows
      .map((r) => toNumber(r[contract.priceField!]))
      .filter((n): n is number => n !== null);
    if (prices.length > 4) {
      const med = median(prices);
      const mult = contract.outlierMultiplier ?? 10;
      const outliers = prices.filter((p) => p > med * mult || p < med / mult).length;
      if (outliers / prices.length > 0.25) {
        issues.push({
          kind: "price_outlier",
          severity: "warn",
          detail: `${outliers}/${prices.length} prices deviate >${mult}x median ${med.toFixed(2)} — possible unit/currency parse drift (${contract.chain})`,
        });
      }
    }
  }

  return issues;
}

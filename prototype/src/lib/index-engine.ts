import { getDb } from "./store";

export interface IndexPoint {
  day: string;
  scope: string;
  value: number;
}

export function computeDailyIndex(day: string): IndexPoint[] {
  const db = getDb();
  const rows = db
    .prepare(
      `
      SELECT o.chain_scope AS scope, o.canonical_id AS item, o.unit_price AS up, o.collected_at
      FROM (
        SELECT obs.*, i.chain AS chain_scope FROM observations obs
        JOIN runs r ON r.id = obs.run_id
        JOIN (SELECT collector_id, chain FROM runs GROUP BY collector_id) i ON i.collector_id = r.collector_id
        WHERE date(obs.collected_at) = ?
      ) o
      WHERE o.unit_price IS NOT NULL AND o.unit_price > 0
    `,
    )
    .all(day) as { scope: string; item: number; up: number }[];

  if (rows.length === 0) return [];

  const byScopeItem = new Map<string, number>();
  for (const r of rows) {
    const k = `${r.scope}|${r.item}`;
    byScopeItem.set(k, (byScopeItem.get(k) ?? 0) + 1);
  }
  const medians = new Map<string, number>();
  for (const key of byScopeItem.keys()) {
    const [scope, item] = key.split("|");
    const prices = rows.filter((r) => r.scope === scope && String(r.item) === item).map((r) => r.up);
    medians.set(key, median(prices));
  }

  const scopes = [...new Set(rows.map((r) => r.scope))];
  const points: IndexPoint[] = [];
  for (const scope of scopes) {
    const value = chainedIndex(db, day, scope, medians);
    if (value !== null) {
      points.push({ day, scope, value });
      db.prepare("INSERT OR REPLACE INTO index_points (day, scope, value) VALUES (?, ?, ?)").run(day, scope, value);
    }
  }
  return points;
}

function chainedIndex(
  db: ReturnType<typeof getDb>,
  day: string,
  scope: string,
  todayMedians: Map<string, number>,
): number | null {
  const prev = db
    .prepare("SELECT value FROM index_points WHERE scope = ? ORDER BY day DESC LIMIT 1")
    .get(scope) as { value: number } | undefined;

  const keys = [...todayMedians.keys()].filter((k) => k.startsWith(`${scope}|`));
  if (keys.length === 0) return null;

  if (!prev) {
    return 100;
  }

  let num = 0;
  let den = 0;
  for (const key of keys) {
    const itemId = key.split("|")[1];
    const basePrice = basePriceFor(db, scope, itemId);
    if (basePrice && basePrice > 0) {
      num += todayMedians.get(key)!;
      den += basePrice;
    }
  }
  if (den === 0) return prev.value;
  const ratio = num / den;
  return Math.round(prev.value * ratio * 10000) / 10000;
}

function basePriceFor(db: ReturnType<typeof getDb>, scope: string, itemId: string): number | null {
  const row = db
    .prepare(
      `
      SELECT MIN(o.unit_price) AS p
      FROM observations o
      JOIN runs r ON r.id = o.run_id
      WHERE r.chain = ? AND o.canonical_id = ? AND o.unit_price IS NOT NULL AND o.unit_price > 0
        AND o.id = (SELECT MIN(o2.id) FROM observations o2 JOIN runs r2 ON r2.id = o2.run_id
                    WHERE r2.chain = ? AND o2.canonical_id = ? AND o2.unit_price IS NOT NULL)
    `,
    )
    .get(scope, Number(itemId), scope, Number(itemId)) as { p: number | null };
  return row?.p ?? null;
}

function median(nums: number[]): number {
  const s = [...nums].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

export interface NormalizedRow {
  rawName: string;
  canonicalName: string;
  category: string | null;
  packGramsMl: number | null;
  unitLabel: string | null;
}

const UNIT_RE = /(\d+(?:[.,]\d+)?)\s*(kg|g|gm|gram|grams|l|ltr|litre|liter|ml|pc|pcs|unit|units)\b/i;

export function parsePackSize(pack: string | null, name: string): { amount: number | null; unit: string | null } {
  const source = `${pack ?? ""} ${name}`;
  const m = source.match(UNIT_RE);
  if (!m) return { amount: null, unit: null };
  const amount = parseFloat(m[1].replace(",", "."));
  return { amount: Number.isFinite(amount) ? amount : null, unit: m[2].toLowerCase() };
}

const GRAM_UNITS = new Set(["kg", "g", "gm", "gram", "grams"]);
const LITER_UNITS = new Set(["l", "ltr", "litre", "liter", "ml"]);

export function toBaseUnits(amount: number, unit: string): { gramsMl: number; label: string } | null {
  if (GRAM_UNITS.has(unit)) {
    const grams = unit === "kg" ? amount * 1000 : amount;
    return { gramsMl: grams, label: "per kg" };
  }
  if (LITER_UNITS.has(unit)) {
    const ml = unit === "l" || unit === "ltr" || unit === "liter" ? amount * 1000 : amount;
    return { gramsMl: ml, label: "per litre" };
  }
  return null;
}

export function unitPrice(price: number | null, pack: string | null, name: string): { unitPrice: number | null; label: string | null } {
  if (price === null || price <= 0) return { unitPrice: null, label: null };
  const { amount, unit } = parsePackSize(pack, name);
  if (amount === null || unit === null) return { unitPrice: null, label: null };
  const base = toBaseUnits(amount, unit);
  if (!base || base.gramsMl <= 0) return { unitPrice: null, label: null };
  const perUnit = unit === "kg" || GRAM_UNITS.has(unit) ? (price / base.gramsMl) * 1000 : (price / base.gramsMl) * 1000;
  return { unitPrice: Math.round(perUnit * 100) / 100, label: base.label };
}

export function normalizeRawName(name: string): string {
  return name
    .toLowerCase()
    .replace(/\s*\(.*?\)\s*/g, " ")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function normalizeRows(rows: Record<string, unknown>[]): NormalizedRow[] {
  return rows.map((r) => {
    const rawName = String(r.title ?? r.name ?? "");
    const pack = (r.pack_size as string) ?? null;
    const { amount, unit } = parsePackSize(pack, rawName);
    const base = amount !== null && unit !== null ? toBaseUnits(amount, unit) : null;
    const catGuess = guessCategory(rawName);
    return {
      rawName,
      canonicalName: normalizeRawName(rawName),
      category: catGuess,
      packGramsMl: base?.gramsMl ?? null,
      unitLabel: base?.label ?? null,
    };
  });
}

const CATEGORY_HINTS: [string, RegExp][] = [
  ["dairy", /milk|curd|yogurt|paneer|butter|cheese|ghee/i],
  ["staples", /rice|atta|flour|dal|pulse|oil|sugar|salt/i],
  ["beverages", /tea|coffee|juice|soda|water|drink/i],
  ["snacks", /chip|biscuit|cookie|namkeen|chocolate|snack/i],
  ["produce", /onion|potato|tomato|apple|banana|vegetable|fruit/i],
  ["household", /detergent|soap|shampoo|clean|tissue|brush/i],
];

function guessCategory(name: string): string | null {
  for (const [cat, re] of CATEGORY_HINTS) if (re.test(name)) return cat;
  return null;
}

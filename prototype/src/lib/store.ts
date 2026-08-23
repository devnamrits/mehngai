import { DatabaseSync } from "node:sqlite";
import { normalizeRawName } from "./normalize";

export interface Observation {
  collectorId: string;
  chain: string;
  rawName: string;
  brand: string | null;
  packSize: string | null;
  price: number | null;
  currency: string;
  unitPrice: number | null;
  unitLabel: string | null;
  url: string | null;
  collectedAt: string;
}

let db: DatabaseSync | null = null;

export function getDb(): DatabaseSync {
  if (db) return db;
  const url = process.env.DATABASE_URL ?? "file:./mehngai.db";
  const path = url.startsWith("file:") ? url.slice(5) : url;
  db = new DatabaseSync(path);
  migrate(db);
  return db;
}

function migrate(d: DatabaseSync): void {
  d.exec(`
    CREATE TABLE IF NOT EXISTS runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      collector_id TEXT NOT NULL,
      chain TEXT NOT NULL,
      started_at TEXT NOT NULL,
      row_count INTEGER NOT NULL,
      status TEXT NOT NULL,
      heal_count INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS items (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      canonical_name TEXT NOT NULL UNIQUE,
      category TEXT,
      unit_label TEXT
    );
    CREATE TABLE IF NOT EXISTS observations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id INTEGER NOT NULL REFERENCES runs(id),
      chain TEXT NOT NULL DEFAULT '',
      raw_name TEXT NOT NULL,
      canonical_id INTEGER REFERENCES items(id),
      brand TEXT,
      pack_size TEXT,
      price REAL,
      currency TEXT NOT NULL DEFAULT 'INR',
      unit_price REAL,
      unit_label TEXT,
      url TEXT,
      collected_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS obs_item_ts ON observations(canonical_id, collected_at);
    CREATE TABLE IF NOT EXISTS index_points (
      day TEXT NOT NULL,
      scope TEXT NOT NULL,
      value REAL NOT NULL,
      method TEXT NOT NULL DEFAULT 'chained-laspeyres',
      PRIMARY KEY (day, scope)
    );
    CREATE TABLE IF NOT EXISTS incidents (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      collector_id TEXT NOT NULL,
      detected_at TEXT NOT NULL,
      reason TEXT NOT NULL,
      heal_prompt TEXT,
      resolved_at TEXT,
      outcome TEXT
    );
    CREATE TABLE IF NOT EXISTS pulse_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT NOT NULL,
      level TEXT NOT NULL,
      kind TEXT NOT NULL,
      message TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS watchlist (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subscriber_hash TEXT NOT NULL,
      item_id INTEGER NOT NULL REFERENCES items(id),
      target_price REAL,
      channel TEXT NOT NULL DEFAULT 'telegram',
      created_at TEXT NOT NULL
    );
  `);
}

function ensureCanonical(chain: string, obs: Observation): number | null {
  const canonical = normalizeRawName(obs.rawName);
  if (!canonical) return null;
  const existing = getDb().prepare("SELECT id FROM items WHERE canonical_name = ?").get(canonical) as
    | { id: number }
    | undefined;
  if (existing) return existing.id;
  const info = getDb()
    .prepare("INSERT INTO items (canonical_name) VALUES (?)")
    .run(canonical);
  return Number(info.lastInsertRowid);
}

export function startRun(collectorId: string, chain: string): number {
  const info = getDb()
    .prepare("INSERT INTO runs (collector_id, chain, started_at, row_count, status) VALUES (?, ?, ?, 0, 'running')")
    .run(collectorId, chain, new Date().toISOString());
  return Number(info.lastInsertRowid);
}

export function finishRun(runId: number, rowCount: number, status: string): void {
  getDb().prepare("UPDATE runs SET row_count = ?, status = ? WHERE id = ?").run(rowCount, status, runId);
}

export function insertObservations(runId: number, obs: Observation[]): void {
  const stmt = getDb().prepare(`
    INSERT INTO observations (run_id, chain, raw_name, canonical_id, brand, pack_size, price, currency, unit_price, unit_label, url, collected_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);
  getDb().exec("BEGIN");
  try {
    for (const o of obs) {
      const canonicalId = ensureCanonical(o.chain, o);
      stmt.run(
        runId,
        o.chain,
        o.rawName,
        canonicalId,
        o.brand,
        o.packSize,
        o.price,
        o.currency,
        o.unitPrice,
        o.unitLabel,
        o.url,
        o.collectedAt,
      );
    }
    getDb().exec("COMMIT");
  } catch (err) {
    getDb().exec("ROLLBACK");
    throw err;
  }
}

export function logIncident(collectorId: string, reason: string, healPrompt?: string): number {
  const info = getDb()
    .prepare("INSERT INTO incidents (collector_id, detected_at, reason, heal_prompt) VALUES (?, ?, ?, ?)")
    .run(collectorId, new Date().toISOString(), reason, healPrompt ?? null);
  return Number(info.lastInsertRowid);
}

export function resolveIncident(id: number, outcome: string): void {
  getDb()
    .prepare("UPDATE incidents SET resolved_at = ?, outcome = ? WHERE id = ?")
    .run(new Date().toISOString(), outcome, id);
}

export function persistPulse(ts: string, level: string, kind: string, message: string): void {
  getDb().prepare("INSERT INTO pulse_events (ts, level, kind, message) VALUES (?, ?, ?, ?)").run(ts, level, kind, message);
}

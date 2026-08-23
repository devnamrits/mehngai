import { runCollector } from "./brightdata";
import { validateRun, type CollectorContract, type ValidationIssue } from "./validate";
import { finishRun, insertObservations, logIncident, persistPulse, resolveIncident, startRun, type Observation } from "./store";
import { pulse } from "./pulse";
import { normalizeRows } from "./normalize";

export interface ChainConfig {
  chain: string;
  collectorIdEnv: string;
  url?: string;
  fields: CollectorContract["fields"];
  priceField?: string;
}

export function contractsFromEnv(): ChainConfig[] {
  const baseFields = [
    { name: "title", required: true },
    { name: "price", required: true, numeric: true },
    { name: "pack_size", maxNullRatio: 0.6 },
    { name: "url", maxNullRatio: 0.6 },
  ];
  const chains = [
    { chain: "A", collectorIdEnv: "COLLECTOR_CHAIN_A" },
    { chain: "B", collectorIdEnv: "COLLECTOR_CHAIN_B" },
    { chain: "C", collectorIdEnv: "COLLECTOR_CHAIN_C" },
  ];
  return chains
    .filter((c) => process.env[c.collectorIdEnv])
    .map((c) => ({ ...c, fields: baseFields, priceField: "price" }));
}

function toObservations(rows: Record<string, unknown>[], chain: string): Observation[] {
  const now = new Date().toISOString();
  return rows.map((r) => ({
    collectorId: "",
    chain,
    rawName: String(r.title ?? r.name ?? "unknown"),
    brand: (r.brand as string) ?? null,
    packSize: (r.pack_size as string) ?? null,
    price: typeof r.price === "number" ? r.price : parseFloat(String(r.price ?? "")) || null,
    currency: (r.currency as string) ?? "INR",
    unitPrice: (r.unit_price as number) ?? null,
    unitLabel: (r.unit_label as string) ?? null,
    url: (r.url as string) ?? null,
    collectedAt: now,
  }));
}

async function collectOnce(cfg: ChainConfig): Promise<{ rows: Record<string, unknown>[]; issues: ValidationIssue[] }> {
  const collectorId = process.env[cfg.collectorIdEnv]!;
  const rows = await runCollector<Record<string, unknown>[]>(collectorId, cfg.url);
  const issues = validateRun(rows, {
    collectorId,
    chain: cfg.chain,
    fields: cfg.fields,
    priceField: cfg.priceField,
  });
  return { rows, issues };
}

export async function runNightly(): Promise<void> {
  const configs = contractsFromEnv();
  if (configs.length === 0) {
    pulse.emit("error", "config", "No COLLECTOR_* env vars set — nothing to run");
    return;
  }
  pulse.emit("info", "pipeline", `Nightly run starting for ${configs.length} chains`);

  for (const cfg of configs) {
    const collectorId = process.env[cfg.collectorIdEnv]!;
    let healed = false;
    try {
      let { rows, issues } = await collectOnce(cfg);
      const critical = issues.filter((i) => i.severity === "critical");

      if (critical.length > 0) {
        const reason = critical.map((i) => i.detail).join("; ");
        pulse.emit("warn", "drift", `${cfg.chain}: ${reason}`);
        persistPulse(new Date().toISOString(), "warn", "drift", reason);
        const incidentId = logIncident(collectorId, reason);

        const prompt = buildHealPrompt(critical, cfg);
        pulse.emit("heal", "watchdog", `Dispatching autonomous heal for ${cfg.chain}`);
        await healWithLog(collectorId, prompt, cfg.url);

        const retry = await collectOnce(cfg);
        rows = retry.rows;
        issues = retry.issues;
        healed = retry.issues.filter((i) => i.severity === "critical").length === 0;
        resolveIncident(incidentId, healed ? "healed+verified" : "heal-failed");
        pulse.emit(healed ? "heal" : "error", "watchdog", healed ? `${cfg.chain}: recovered` : `${cfg.chain}: still failing`);
      }

      const runId = startRun(collectorId, cfg.chain);
      const obs = toObservations(rows, cfg.chain);
      insertObservations(runId, obs);
      finishRun(runId, obs.length, healed ? "healed" : "ok");
      pulse.emit("info", "ingest", `${cfg.chain}: stored ${obs.length} rows`);
      void normalizeRows;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      pulse.emit("error", "pipeline", `${cfg.chain}: ${msg}`);
      persistPulse(new Date().toISOString(), "error", "pipeline", msg);
    }
  }
  pulse.emit("info", "pipeline", "Nightly run complete");
}

function buildHealPrompt(issues: ValidationIssue[], cfg: ChainConfig): string {
  const fieldHints = issues
    .map((i) => {
      const m = i.detail.match(/field "([^"]+)"/);
      return m ? `"${m[1]}"` : null;
    })
    .filter(Boolean)
    .join(", ");
  const target = fieldHints || "the main fields";
  return (
    `The scraper for ${cfg.chain} started returning empty/null values for ${target} ` +
    `since the site layout changed. Re-capture these fields from the current markup, ` +
    `keeping the same output schema.`
  ).slice(0, 999);
}

let supervisedHeals = new Set<string>();

async function healWithLog(collectorId: string, prompt: string, url?: string): Promise<void> {
  const { healCollector } = await import("./brightdata");
  const auto = supervisedHeals.has(collectorId);
  const out = await healCollector(collectorId, prompt, { url, autoApprove: auto });
  if (!auto) supervisedHeals.add(collectorId);
  persistPulse(new Date().toISOString(), "info", "heal", `heal executed (auto=${auto}) approved=${out.approved}`);
}

import "dotenv/config";
import { getDb, startRun, finishRun, insertObservations, persistPulse, logIncident, resolveIncident } from "../src/lib/store";
import { computeDailyIndex } from "../src/lib/index-engine";
import { unitPrice } from "../src/lib/normalize";
import { pulse, type PulseEvent } from "../src/lib/pulse";

pulse.subscribe((e: PulseEvent) => process.stdout.write(`[pulse] ${e.level} ${e.kind}: ${e.message}\n`));

process.env.DATABASE_URL = "file:./smoke.db";
getDb();

const mkObs = (chain: string, rawName: string, price: number, pack: string | null) => {
  const { unitPrice: up, label } = unitPrice(price, pack, rawName);
  return {
    collectorId: "c_smoke", chain, rawName, brand: null, packSize: pack,
    price, currency: "INR", unitPrice: up, unitLabel: label, url: null,
    collectedAt: new Date().toISOString(),
  };
};

const run1 = startRun("c_smoke_a", "A");
insertObservations(run1, [
  mkObs("A", "Amul Gold Milk 1 L", 66, "1 L"),
  mkObs("A", "Tata Salt 1 kg", 28, "1 kg"),
  mkObs("A", "Fortune Sunflower Oil 1L", 140, "1 L"),
]);
finishRun(run1, 3, "ok");

logIncident("c_smoke_b", "field \"price\" missing on every row (B)");
resolveIncident(1, "healed+verified");
persistPulse(new Date().toISOString(), "heal", "watchdog", "B: recovered in smoke test");

const day = new Date().toISOString().slice(0, 10);
console.log("index points:", computeDailyIndex(day));

const counts = getDb().prepare(
  "SELECT (SELECT COUNT(*) FROM observations) AS obs, (SELECT COUNT(*) FROM items) AS items, (SELECT COUNT(*) FROM incidents) AS inc",
).get() as { obs: number; items: number; inc: number };
console.log("db counts:", counts);

import "dotenv/config";
import { runNightly } from "../src/lib/orchestrator";
import { computeDailyIndex } from "../src/lib/index-engine";
import { pulse, type PulseEvent } from "../src/lib/pulse";

pulse.subscribe((e: PulseEvent) => {
  const line = `[${e.ts}] ${e.level.toUpperCase()} ${e.kind}: ${e.message}`;
  process.stdout.write(line + "\n");
});

runNightly()
  .then(() => computeDailyIndex(new Date().toISOString().slice(0, 10)))
  .then((points): void => {
    for (const p of points) console.log(`index ${p.scope} @ ${p.day} = ${p.value}`);
  })
  .catch((err: unknown) => {
    console.error("nightly failed:", err);
    process.exitCode = 1;
  });

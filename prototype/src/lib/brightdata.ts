import { execFileSync } from "node:child_process";

const API_BASE = process.env.BRIGHTDATA_API_BASE ?? "https://api.brightdata.com";

function key(): string {
  const k = process.env.BRIGHTDATA_API_KEY;
  if (!k) throw new Error("BRIGHTDATA_API_KEY missing — copy .env.example to .env");
  return k;
}

async function bdFetch(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${key()}`,
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) throw new Error(`BrightData ${path} failed: ${res.status} ${await res.text()}`);
  return res;
}

export interface TriggerResult {
  snapshotId: string;
}

export async function triggerCollector(collectorId: string, url?: string): Promise<TriggerResult> {
  const body: Record<string, unknown> = { collector_id: collectorId };
  if (url) body.url = url;
  const res = await bdFetch("/dca/trigger", {
    method: "POST",
    body: JSON.stringify(body),
  });
  const json = (await res.json()) as { snapshot_id?: string; id?: string };
  const snapshotId = json.snapshot_id ?? json.id;
  if (!snapshotId) throw new Error(`No snapshot id returned for ${collectorId}`);
  return { snapshotId };
}

export async function waitForSnapshot<T = unknown[]>(
  snapshotId: string,
  opts: { timeoutMs?: number; intervalMs?: number } = {},
): Promise<T> {
  const { timeoutMs = 15 * 60_000, intervalMs = 10_000 } = opts;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const res = await bdFetch(`/dca/dataset/${snapshotId}?format=json`);
    const text = await res.text();
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) return parsed as T;
      const status = (parsed as { status?: string }).status;
      if (status === "running" || status === "pending") {
        await sleep(intervalMs);
        continue;
      }
      return parsed as T;
    } catch {
      await sleep(intervalMs);
    }
  }
  throw new Error(`Snapshot ${snapshotId} timed out after ${timeoutMs}ms`);
}

export async function runCollector<T = unknown[]>(collectorId: string, url?: string): Promise<T> {
  const { snapshotId } = await triggerCollector(collectorId, url);
  return waitForSnapshot<T>(snapshotId);
}

export interface HealOutcome {
  approved: boolean;
  raw: unknown;
}

export async function healCollector(
  collectorId: string,
  prompt: string,
  opts: { url?: string; autoApprove?: boolean } = {},
): Promise<HealOutcome> {
  const args = ["-p", "@brightdata/cli", "bdata", "scraper", "heal", collectorId, prompt];
  if (opts.url) args.push("--url", opts.url);
  if (opts.autoApprove) args.push("--auto-approve");

  const stdout = execFileSync("npx", args, {
    encoding: "utf8",
    timeout: 20 * 60_000,
    env: { ...process.env },
    stdio: ["ignore", "pipe", "pipe"],
  });

  const awaiting = stdout.includes("awaiting_approval");
  if (!awaiting) return { approved: true, raw: stdout };

  const approveArgs = ["-p", "@brightdata/cli", "bdata", "scraper", "approve", collectorId];
  if (opts.url) approveArgs.push("--url", opts.url);
  const approveOut = execFileSync("npx", approveArgs, {
    encoding: "utf8",
    timeout: 20 * 60_000,
    env: { ...process.env },
    stdio: ["ignore", "pipe", "pipe"],
  });
  return { approved: true, raw: approveOut };
}

export function rejectHeal(collectorId: string, url?: string): void {
  const args = ["-p", "@brightdata/cli", "bdata", "scraper", "approve", collectorId, "--reject"];
  if (url) args.push("--url", url);
  execFileSync("npx", args, { encoding: "utf8", env: { ...process.env }, stdio: "ignore" });
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

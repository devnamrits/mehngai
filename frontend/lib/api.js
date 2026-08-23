const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function get(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export const api = {
  health: () => get("/api/v1/health"),
  index: (days = 30, scope = "") => get(`/api/v1/index?days=${days}&scope=${scope}`),
  prices: (q) => get(`/api/v1/prices?q=${encodeURIComponent(q)}`),
  basketCompare: (payload) =>
    fetch(`${BASE}/api/v1/basket`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) => { if (!r.ok) throw new Error(`basket ${r.status}`); return r.json(); }),
  movers: (windowDays = 7) => get(`/api/v1/movers?window_days=${windowDays}`),
  briefing: () => get("/api/v1/insights/daily"),
  pulseRecent: () => get("/api/v1/pulse/recent"),
  stats: () => get("/api/v1/stats"),
  movements: () => get("/api/v1/movements"),
  inflation: () => get("/api/v1/inflation"),
  deals: () => get("/api/v1/deals"),
};

export function openPulseStream(onEvent, onStatus) {
  const es = new EventSource(`${BASE}/api/v1/pulse/stream`);
  es.addEventListener("pulse", (e) => {
    try {
      onEvent(JSON.parse(e.data));
    } catch {
      /* ignore malformed frame */
    }
  });
  es.onopen = () => onStatus?.(true);
  es.onerror = () => onStatus?.(false);
  return () => es.close();
}

export function fmt(n, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
  return `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: digits })}`;
}

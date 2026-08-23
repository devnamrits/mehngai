"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api, fmt, openPulseStream } from "../lib/api";

const QUICK = ["milk", "paneer", "rice", "oil", "tea", "biscuit", "egg", "tomato"];

/* ---------------- masthead ---------------- */
function Masthead({ live }) {
  const today = new Date().toLocaleDateString("en-IN", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });
  return (
    <header className="masthead">
      <div className="brand">
        <h1>Mehngai<span>.</span></h1>
        <span className="tag-badge">india&apos;s live grocery inflation index</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ color: "var(--faint)", fontSize: 12 }}>{today}</span>
        <span className="live-pill">
          <span className={`dot${live ? "" : " off"}`} />
          {live ? "live" : "reconnecting"}
        </span>
      </div>
    </header>
  );
}

/* ---------------- the mehngai number (hero) ---------------- */
function MehngaiHero() {
  const [d, setD] = useState(null);

  useEffect(() => { api.inflation().then(setD).catch(() => {}); }, []);

  return (
    <section className="hero">
      <p className="kicker" style={{ textAlign: "center" }}>the mehngai number · month over month</p>

      {d?.status === "live" && (
        <>
          <div
            className="mega"
            style={{ color: d.basket_change_pct > 0 ? "var(--down)" : "var(--up)" }}
          >
            {d.basket_change_pct > 0 ? "+" : ""}{d.basket_change_pct}<span>%</span>
          </div>
          <p className="hero-sub">
            grocery shelf prices moved this much since <b>{d.baseline_day}</b> —
            across <b>{d.items_compared} everyday items</b> on real store shelves.
          </p>
        </>
      )}

      {d?.status === "collecting" && (
        <>
          <div className="mega mega-muted">baseline<span>.</span></div>
          <p className="hero-sub">
            Locked on <b>{d.latest_day}</b> — <b>{d.scan_days} of {d.days_required}</b> scans done.
            Every nightly scan compounds into India&apos;s fastest grocery-inflation number.
            No committees. No lag. Just shelves.
          </p>
          <div className="daybar center">
            {[...Array(d.days_required)].map((_, i) => (
              <i key={i} style={{ background: i < d.scan_days ? "var(--saffron)" : "var(--line)" }} />
            ))}
          </div>
        </>
      )}
      {!d && <div className="mega mega-muted">—</div>}
    </section>
  );
}

/* ---------------- movement ticker ---------------- */
function Ticker() {
  const [moves, setMoves] = useState([]);

  useEffect(() => { api.movements().then((d) => setMoves(d.movements ?? [])).catch(() => {}); }, []);

  if (moves.length === 0) return null;
  const strip = [...moves, ...moves]; // seamless loop
  return (
    <div className="ticker" aria-hidden="true">
      <div className="ticker-track">
        {strip.map((mv, i) => (
          <span key={i} className="tick-item">
            {mv.item.slice(0, 26)}
            <b style={{ color: mv.delta_pct > 0 ? "var(--down)" : "var(--up)" }}>
              {mv.delta_pct > 0 ? "▲" : "▼"}{Math.abs(mv.delta_pct)}%
            </b>
          </span>
        ))}
      </div>
    </div>
  );
}

function MeterCard() {
  const [data, setData] = useState(null);

  useEffect(() => { api.movements().then(setData).catch(() => {}); }, []);
  const sum = data?.summary;

  return (
    <div className="rail-card">
      <p className="kicker">Mehngai meter · today&apos;s moves</p>
      {sum && (
        <p style={{ margin: "0 0 10px", fontSize: "13.5px", color: "var(--muted)" }}>
          Since first scan:{" "}
          <b style={{ color: "var(--down)" }}>{sum.up} up</b> ·{" "}
          <b style={{ color: "var(--up)" }}>{sum.down} down</b>.
        </p>
      )}
      <ul className="move-list">
        {(data?.movements ?? []).slice(0, 7).map((mv) => (
          <li key={mv.item + mv.store}>
            <span className="m-name">{mv.item}</span>
            <span className="m-store">{mv.store}</span>
            <span className="m-delta" style={{ color: mv.delta_pct > 0 ? "var(--down)" : "var(--up)" }}>
              {mv.delta_pct > 0 ? "+" : ""}{mv.delta_pct}%
            </span>
          </li>
        ))}
        {!data && <li style={{ color: "var(--faint)" }}>Reading the ledger…</li>}
        {data && (data.movements ?? []).length === 0 && (
          <li style={{ color: "var(--faint)" }}>Shelves steady.</li>
        )}
      </ul>
    </div>
  );
}

/* ---------------- basket tool (secondary) ---------------- */
function BasketBuilder({ chainMeta }) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [basket, setBasket] = useState([]);
  const [result, setResult] = useState(null);
  const [notice, setNotice] = useState("");
  const [chips, setChips] = useState([]);
  const timer = useRef(null);

  useEffect(() => {
    (async () => {
      const verified = [];
      for (const t of QUICK) {
        try {
          const d = await api.prices(t);
          verified.push({ term: t, count: (d.results ?? []).length });
        } catch {}
      }
      setChips(verified.filter((c) => c.count > 0));
    })();
  }, []);

  const payload = useMemo(() => ({ items: basket.map((b) => ({ q: b.item, qty: b.qty })) }), [basket]);

  useEffect(() => {
    clearTimeout(timer.current);
    if (query.trim().length < 2) { setSuggestions([]); return; }
    timer.current = setTimeout(async () => {
      try {
        const d = await api.prices(query.trim());
        setSuggestions((d.results ?? []).slice(0, 6));
        if (d.chains) onChainsSafe(d.chains);
      } catch {}
    }, 220);
    return () => clearTimeout(timer.current);
  }, [query]);

  const onChainsSafe = (chains) => window.dispatchEvent(new CustomEvent("chains", { detail: chains }));

  useEffect(() => {
    const handler = (e) => window.dispatchEvent(new CustomEvent("chains-merge", { detail: e.detail }));
    window.addEventListener("chains", handler);
    return () => window.removeEventListener("chains", handler);
  }, []);

  useEffect(() => {
    if (basket.length === 0) { setResult(null); return; }
    const t = setTimeout(async () => {
      try { setResult(await api.basketCompare(payload)); } catch {}
    }, 200);
    return () => clearTimeout(t);
  }, [payload]);

  const addFromSuggestion = (sg) => {
    setBasket((prev) => prev.some((b) => b.item === sg.item) ? prev : [...prev, { item: sg.item, qty: 1 }]);
    setQuery(""); setSuggestions([]);
  };
  const bump = (item, delta) =>
    setBasket((prev) => prev.map((b) => (b.item === item ? { ...b, qty: Math.max(1, Math.min(60, b.qty + delta)) } : b)));
  const remove = (item) => setBasket((prev) => prev.filter((b) => b.item !== item));
  const addQuick = async (term) => {
    try {
      const d = await api.prices(term);
      const first = (d.results ?? [])[0];
      if (first) addFromSuggestion(first);
    } catch {}
  };

  const totals = result?.totals ?? {};
  const sorted = Object.entries(totals).sort((a, b) => a[1] - b[1]);
  const slugs = Object.keys(chainMeta);

  return (
    <section className="card">
      <p className="kicker">Check your basket · what does it cost where</p>

      <div className="chips">
        {chips.map(({ term, count }) => (
          <button key={term} className="chip" onClick={() => addQuick(term)}>
            + {term} <span style={{ color: "var(--faint)", marginLeft: 4 }}>{count}</span>
          </button>
        ))}
      </div>

      <div className="searchbox">
        <span className="icon">/</span>
        <input placeholder="search any staple…" value={query} onChange={(e) => setQuery(e.target.value)} />
        {suggestions.length > 0 && (
          <ul className="suggest">
            {suggestions.map((sg) => (
              <li key={sg.item}>
                <button onClick={() => addFromSuggestion(sg)}>
                  <span>{sg.item}</span>
                  <span style={{ display: "flex", gap: 6 }}>
                    {Object.keys(sg.chains).map((c) => (
                      <span key={c} className="deal-tag"
                        style={{ borderColor: chainMeta[c]?.accent, color: chainMeta[c]?.accent }}>
                        {chainMeta[c]?.short ?? c}
                      </span>
                    ))}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {basket.length > 0 && (
        <>
          <ul className="basket-list">
            {basket.map((b) => (
              <li key={b.item} className="basket-item">
                <span className="n">{b.item}</span>
                <span className="qty">
                  <button onClick={() => bump(b.item, -1)}>−</button>
                  <b>{b.qty}</b>
                  <button onClick={() => bump(b.item, +1)}>+</button>
                </span>
                <button className="x" onClick={() => remove(b.item)}
                  style={{ background: "none", border: "none", color: "var(--faint)", cursor: "pointer" }}>✕</button>
              </li>
            ))}
          </ul>

          {result && (
            <>
              <table className="matrix">
                <colgroup>
                  <col style={{ width: "40%" }} /><col /><col /><col /><col />
                </colgroup>
                <thead>
                  <tr>
                    <th>Item</th>
                    {slugs.map((slug) => (
                      <th key={slug} className="num" style={{ color: chainMeta[slug]?.accent }}>
                        {chainMeta[slug]?.short}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(result.items ?? []).filter((i) => i.found).map((line) => {
                    const entries = slugs.map((slug) => [slug, line.prices?.[slug]?.price]);
                    const present = entries.filter(([, v]) => v !== undefined && v !== null);
                    const min = present.length ? Math.min(...present.map(([, v]) => Number(v))) : Infinity;
                    return (
                      <tr key={line.item}>
                        <td className="m-item">{line.item}</td>
                        {entries.map(([slug, v]) => (
                          <td key={slug} className="num m-cell">
                            {v === undefined || v === null ? (
                              <span className="cross">✕</span>
                            ) : (
                              <span className={Number(v) === min && present.length > 1 ? "win" : ""}>
                                {Number(v) === min && present.length > 1 ? "✓ " : ""}₹{Number(v).toLocaleString("en-IN")}
                              </span>
                            )}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                  <tr className="m-total-row">
                    <td>Basket total</td>
                    {slugs.map((slug) => {
                      const cov = (result.items ?? []).filter(
                        (l) => l.found && l.prices?.[slug]?.price !== undefined,
                      ).length;
                      const total = sorted.length && totals[slug];
                      return (
                        <td key={slug} className="num">
                          {total ? `₹${Number(total).toLocaleString("en-IN")}` : "—"}
                          <small className="cov">{cov}/{(result.items ?? []).filter((i) => i.found).length}</small>
                        </td>
                      );
                    })}
                  </tr>
                </tbody>
              </table>

              <div className="takeaway">
                {result.comparable && result.cheapest_chain ? (
                  <>One-stop at <b>{chainMeta[result.cheapest_chain]?.name}</b>:{" "}
                  <b>{fmt(result.totals[result.cheapest_chain])}</b>. Smart mix across stores:{" "}
                  <b>{fmt(result.smart_total)}</b> — you keep {fmt(result.spread)} extra in your pocket.</>
                ) : result.note}
              </div>
            </>
          )}
        </>
      )}

      {basket.length === 0 && (
        <p className="empty-note">
          Tap a staple or search — every store&apos;s price, side by side.
        </p>
      )}
    </section>
  );
}

function Deals({ chainMeta }) {
  const [deals, setDeals] = useState(null);

  useEffect(() => { api.deals().then((d) => setDeals(d.deals ?? [])).catch(() => {}); }, []);

  return (
    <section>
      <p className="kicker">Smarter pick radar · same product, two shelves</p>
      {!deals && <div className="card empty-note">Scanning…</div>}
      {deals && deals.length === 0 && (
        <div className="card empty-note">Radar sharpens each night as catalogs overlap more.</div>
      )}
      {deals && deals.slice(0, 6).map((dl) => (
        <div key={dl.item} className="deal-card">
          <div className="deal-item">{dl.item}</div>
          <div className="gap-pill">−{dl.gap_pct}%<small>PAY LESS</small></div>
          <div className="deal-stores">
            <span className="deal-tag" style={{ borderColor: dl.buy_at.accent, color: dl.buy_at.accent }}>
              ✓ {dl.buy_at.name} ₹{dl.low_price}
            </span>
            vs
            <span className="deal-tag">{dl.avoid.name} ₹{dl.high_price}</span>
            <span>save ₹{dl.you_save}</span>
          </div>
        </div>
      ))}
    </section>
  );
}

function ShelfSnapshot({ stats, chainMeta }) {
  const perChain = stats.per_chain ?? {};
  return (
    <section>
      <p className="kicker">Coverage · tonight&apos;s scanned shelves</p>
      <div className="stores">
        {Object.entries(perChain).map(([slug, count]) => {
          const m = chainMeta[slug] ?? {};
          return (
            <div key={slug} className="store-card" style={{ "--accent": m.accent }}>
              <div className="store-name">{m.name ?? slug}</div>
              <div className="store-value">{count}</div>
              <div className="store-sub">products</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

const LEVEL_LABEL = { heal: "recovered", warn: "drift", error: "fault", info: "" };

function humanize(e, chainMeta) {
  const m = e.message ?? "";
  const nameOf = (slug) => chainMeta?.[slug]?.name ?? slug;
  if (/nightly run starting/i.test(m)) return { text: "Nightly shelf scan started", level: "info" };
  if (/nightly complete|run complete/i.test(m)) return { text: "Tonight's scan finished", level: "heal" };
  if (/stored (\d+) rows/.test(m)) {
    const n = m.match(/stored (\d+)/)[1];
    const chain = m.split(":")[0].trim();
    if (/0 rows/.test(m)) return null;
    return { text: `${nameOf(chain)}: ${n} products captured`, level: "info" };
  }
  if (/drift:/i.test(m)) return { text: "Store redesigned its page — self-repair started", level: "warn" };
  if (/heal applied|recovered/i.test(m)) return { text: "Scraper repaired itself — same API, zero downtime", level: "heal" };
  if (/409|refactor|heal failed|trigger failed|no input/i.test(m)) return null;
  if (e.level === "error") return null;
  return { text: m.replace(/chain-[a-d]/g, nameOf), level: e.level };
}

function PulseCard({ events, live, chainMeta }) {
  return (
    <div className="rail-card">
      <p className="kicker" style={{ marginBottom: 4 }}>System pulse · self-healing watch</p>
      <ul className="pulse-mini">
        {[...events].reverse()
          .map((e) => ({ ...e, h: humanize(e, chainMeta) }))
          .filter((e) => e.h && e.h.text)
          .slice(0, 8)
          .map((e, i) => (
            <li key={`${e.ts}-${i}`}>
              <span className={`lv ${e.h.level}`} />
              <div>
                <time>{new Date(e.ts).toLocaleTimeString("en-IN")}</time>
                {e.h.text}
              </div>
            </li>
          ))}
        {events.length === 0 && <li><span className="lv info" /><div>Idle — next scan scheduled.</div></li>}
      </ul>
    </div>
  );
}

function HowItWorks() {
  return (
    <div className="rail-card">
      <p className="kicker">How it works</p>
      <ul className="how" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        <li><b>1 · Scan.</b> Self-healing scrapers read four chains&apos; shelves nightly via Bright Data.</li>
        <li><b>2 · Guard.</b> Watchdog validates every run; site redesigns trigger autonomous repair.</li>
        <li><b>3 · Compound.</b> Each scan stacks into the Mehngai number — month-over-month truth.</li>
      </ul>
    </div>
  );
}

export default function Page() {
  const [series, setSeries] = useState([]);
  const [stats, setStats] = useState({});
  const [chainMeta, setChainMeta] = useState({});
  const [pulseEvents, setPulseEvents] = useState([]);
  const [live, setLive] = useState(false);

  const mergeChains = (d) => { if (d?.chains) setChainMeta((prev) => ({ ...prev, ...d.chains })); };

  useEffect(() => {
    api.stats().then((d) => { setStats(d); mergeChains(d); }).catch(() => {});
    api.index(30).then((d) => setSeries(d.series ?? [])).catch(() => {});
    api.pulseRecent().then((d) => setPulseEvents(d.events ?? [])).catch(() => {});
  }, []);

  useEffect(
    () => openPulseStream((event) => setPulseEvents((prev) => [...prev.slice(-200), event]), setLive),
    [],
  );

  return (
    <div className="page">
      <Masthead live={live} />
      <MehngaiHero />
      <Ticker />
      <div className="layout">
        <main>
          <BasketBuilder chainMeta={chainMeta} />
          <Deals chainMeta={chainMeta} />
          <ShelfSnapshot stats={stats} chainMeta={chainMeta} />
        </main>
        <aside>
          <MeterCard />
          <HowItWorks />
          <PulseCard events={pulseEvents} live={live} chainMeta={chainMeta} />
        </aside>
      </div>
      <footer className="footer">
        <span>Mehngai · live grocery inflation, measured from real shelves · Bright Data Scraper Studio self-healing collectors</span>
        <span>public API · /api/v1/*</span>
      </footer>
    </div>
  );
}

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api, fmt, openPulseStream } from "../lib/api";

const QUICK = ["milk", "paneer", "rice", "oil", "tea", "biscuit", "egg", "tomato"];

function Masthead({ live }) {
  return (
    <header className="masthead">
      <div className="brand">
        <h1>Mehngai<span>.</span></h1>
        <span className="tag-badge">price watchdog</span>
      </div>
      <span className="live-pill">
        <span className={`dot${live ? "" : " off"}`} />
        {live ? "live collection" : "reconnecting"}
      </span>
    </header>
  );
}

function Hero({ stats }) {
  return (
    <section className="hero">
      <h2>
        Same basket. Different stores.<br />
        <em>Wildly different prices.</em>
      </h2>
      <p className="sub">
        We read real supermarket shelves every night and price your monthly
        basket at every store — so you never overpay for groceries again.
      </p>
      <div className="stat-row">
        <div className="stat"><b>{stats.products ?? "—"}</b><span>products tracked</span></div>
        <div className="stat"><b>{Object.keys(stats.per_chain ?? {}).length || "—"}</b><span>stores watched</span></div>
        <div className="stat"><b>{stats.observations ?? "—"}</b><span>shelf readings</span></div>
        <div className="stat"><b>nightly</b><span>auto-updated</span></div>
      </div>
    </section>
  );
}

const CHIP_TERMS = ["milk", "paneer", "rice", "oil", "tea", "biscuit", "egg", "tomato"];

function BasketBuilder({ chainMeta, onChains }) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [searching, setSearching] = useState(false);
  const [basket, setBasket] = useState([]);
  const [result, setResult] = useState(null);
  const [notice, setNotice] = useState("");
  const [chips, setChips] = useState(CHIP_TERMS.map((t) => ({ term: t, count: null })));
  const timer = useRef(null);

  useEffect(() => {
    (async () => {
      const verified = [];
      for (const t of CHIP_TERMS) {
        try {
          const d = await api.prices(t);
          verified.push({ term: t, count: (d.results ?? []).length });
        } catch { verified.push({ term: t, count: 0 }); }
      }
      setChips(verified.filter((c) => c.count > 0));
    })();
  }, []);

  const payload = useMemo(() => ({ items: basket.map((b) => ({ q: b.item, qty: b.qty })) }), [basket]);

  useEffect(() => {
    clearTimeout(timer.current);
    if (query.trim().length < 2) { setSuggestions([]); setSearching(false); return; }
    setSearching(true);
    timer.current = setTimeout(async () => {
      try {
        const d = await api.prices(query.trim());
        setSuggestions((d.results ?? []).slice(0, 6));
        onChains?.(d);
      } catch {}
      setSearching(false);
    }, 220);
    return () => clearTimeout(timer.current);
  }, [query]);

  useEffect(() => {
    if (basket.length === 0) { setResult(null); return; }
    const t = setTimeout(async () => {
      try { const r = await api.basketCompare(payload); setResult(r); onChains?.(r); } catch {}
    }, 200);
    return () => clearTimeout(t);
  }, [payload]);

  const addFromSuggestion = (s) => {
    setBasket((prev) => prev.some((b) => b.item === s.item) ? prev : [...prev, { item: s.item, qty: 1 }]);
    setQuery(""); setSuggestions([]);
  };
  const bump = (item, delta) =>
    setBasket((prev) => prev.map((b) => (b.item === item ? { ...b, qty: Math.max(1, Math.min(60, b.qty + delta)) } : b)));
  const remove = (item) => setBasket((prev) => prev.filter((b) => b.item !== item));
  const addQuick = async (term) => {
    setNotice("");
    try {
      const d = await api.prices(term);
      const first = (d.results ?? [])[0];
      if (first) addFromSuggestion(first);
      else setNotice(`“${term}” isn't on today's scanned shelves — try another staple.`);
    } catch {}
  };

  const totals = result?.totals ?? {};
  const sorted = Object.entries(totals).sort((a, b) => a[1] - b[1]);
  const cheapest = result?.cheapest_chain;
  const savingsPct = result?.savings ?? 0;

  return (
    <section className="card">
      <p className="kicker">Build your basket · see what it should cost</p>

      <div className="chips">
        {chips.map(({ term, count }) => (
          <button key={term} className="chip" onClick={() => addQuick(term)}>
            + {term} <span style={{ color: "var(--faint)", marginLeft: 4 }}>{count}</span>
          </button>
        ))}
      </div>
      {notice && <p className="empty-note" style={{ padding: "6px 2px" }}>{notice}</p>}

      <div className="searchbox">
        <span className="icon">/</span>
        <input
          placeholder="Search a product — try “ghee” or “olive oil”"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {searching && suggestions.length === 0 && (
          <span style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", color: "var(--faint)", fontSize: 12 }}>…</span>
        )}
        {suggestions.length > 0 && (
          <ul className="suggest">
            {suggestions.map((s) => (
              <li key={s.item}>
                <button onClick={() => addFromSuggestion(s)}>
                  <span>{s.item}</span>
                  <span style={{ display: "flex", gap: 6 }}>
                    {Object.keys(s.chains).map((c) => (
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
            {basket.map((b) => {
              return (
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
              );
            })}
          </ul>

          <div className={`verdict${result ? "" : " dim"}`}>
            {(() => {
              if (!result) return null;
              const slugs = Object.keys(result.chains ?? {}).filter(
                (slug) => Object.values(result.totals ?? {}).some(() => true) || true
              );
              const lines = (result.items ?? []).filter((i) => i.found);
              const cellPrice = (line, slug) => line.prices?.[slug]?.price;
              const fmtCell = (v) => (v === undefined ? "" : `₹${Number(v).toLocaleString("en-IN")}`);

              return (
                <>
                  <p className="kicker" style={{ padding: "16px 18px 0" }}>
                    Store-by-store · your basket on every shelf
                  </p>
                  <table className="matrix">
                    <colgroup>
                      <col style={{ width: "34%" }} />
                      <col />
                      <col />
                      <col />
                      <col />
                    </colgroup>
                    <thead>
                      <tr>
                        <th>Item</th>
                        {slugs.map((slug) => (
                          <th key={slug} className="num" style={{ color: result.chains[slug]?.accent }}>
                            {result.chains[slug]?.short}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {lines.map((line) => {
                        const entries = slugs.map((slug) => [slug, cellPrice(line, slug)]);
                        const present = entries.filter(([, v]) => v !== undefined);
                        const min = Math.min(...present.map(([, v]) => Number(v)));
                        return (
                          <tr key={line.item}>
                            <td className="m-item">{line.item}</td>
                            {entries.map(([slug, v]) => (
                              <td key={slug} className="num m-cell">
                                {v === undefined ? (
                                  <span className="cross">✕</span>
                                ) : (
                                  <span className={Number(v) === min && present.length > 1 ? "win" : ""}>
                                    {Number(v) === min && present.length > 1 ? "✓ " : ""}
                                    {fmtCell(v)}
                                  </span>
                                )}
                              </td>
                            ))}
                          </tr>
                        );
                      })}
                      <tr className="m-total-row">
                        <td>Basket here ({lines.length} items)</td>
                        {slugs.map((slug) => {
                          const covered = lines.filter((l) => l.prices?.[slug]?.price !== undefined).length;
                          const total = lines.reduce(
                            (a, l) => a + (l.prices?.[slug]?.price ?? 0),
                            0,
                          );
                          return (
                            <td key={slug} className="num">
                              {covered > 0 ? fmtCell(total) : "—"}
                              <small className="cov"> {covered}/{lines.length}</small>
                            </td>
                          );
                        })}
                      </tr>
                    </tbody>
                  </table>

                  <div className="takeaway">
                    {result.comparable && result.cheapest_chain ? (
                      <><b>{result.chains[result.cheapest_chain]?.name}</b> stocks all {lines.length} items
                      for <b>{fmt(result.totals[result.cheapest_chain])}</b> — the simplest single-store run.</>
                    ) : (
                      <>No single store stocks all {lines.length}. Smart mix — buy each line at its ✓ —{" "}
                      costs <b>{fmt(result.smart_total)}</b>{result.spread > 0 && (
                        <> vs {fmt(result.smart_total + result.spread)} at worst</>
                      )}.</>
                    )}
                  </div>

                  {!result.comparable && result.item_deal && (
                    <div className="save-banner">
                      Biggest single swap: <b>{result.item_deal.item}</b> at{" "}
                      <b style={{ color: chainMeta[result.item_deal.buy_at.slug]?.accent }}>
                        {chainMeta[result.item_deal.buy_at.slug]?.name} {fmt(result.item_deal.low_price)}
                      </b>{" "}
                      vs {fmt(result.item_deal.high_price)} at {chainMeta[result.item_deal.avoid.slug]?.name}{" "}
                      ({result.item_deal.gap_pct}% less).
                    </div>
                  )}
                  {result.note && (
                    <div className="save-banner" style={{ background: "var(--panel-2)" }}>{result.note}</div>
                  )}
                </>
              );
            })()}</div>
        </>
      )}

      {basket.length === 0 && (
        <p className="empty-note">
          Tap a category above or search — we&apos;ll price your list at every store, using tonight&apos;s real shelves.
        </p>
      )}
    </section>
  );
}

function Deals({ chainMeta, onDeals, onChains }) {
  const [deals, setDeals] = useState(null);

  useEffect(() => { api.deals().then((d) => { setDeals(d.deals ?? []); onDeals?.(d.deals ?? []); onChains?.(d); }).catch(() => {}); }, []);

  return (
    <section>
      <p className="kicker">Smarter pick radar · same product, better store</p>
      {!deals && <div className="card empty-note">Scanning both shelves…</div>}
      {deals && deals.length === 0 && (
        <div className="card empty-note">
          No cross-store duplicates yet — the radar sharpens as catalogs grow each night.
        </div>
      )}
      {deals && deals.slice(0, 6).map((d) => (
        <div key={d.item} className="deal-card">
          <div className="deal-item">{d.item}</div>
          <div className="gap-pill">−{d.gap_pct}%<small>PAY LESS</small></div>
          <div className="deal-stores">
            <span className="deal-tag" style={{ borderColor: d.buy_at.accent, color: d.buy_at.accent }}>
              ✓ {d.buy_at.name} {d.basis === "per pack" ? `₹${d.low_price}` : `₹${d.low_price}/${d.basis.replace("per ", "")}`}
              {d.low_pack ? ` · ${d.low_pack}` : ""}
            </span>
            vs
            <span className="deal-tag">
              {d.avoid.name} {d.basis === "per pack" ? `₹${d.high_price}` : `₹${d.high_price}/${d.basis.replace("per ", "")}`}
              {d.high_pack && d.high_pack !== d.low_pack ? ` · ${d.high_pack}` : ""}
            </span>
            <span>you save {d.gap_pct}% on comparable units</span>
          </div>
        </div>
      ))}
    </section>
  );
}

function ShelfSnapshot({ stats, chainMeta, deals }) {
  const perChain = stats.per_chain ?? {};
  const avgGap = deals?.length
    ? Math.round(deals.reduce((a, d) => a + d.gap_pct, 0) / deals.length)
    : null;

  return (
    <section>
      <p className="kicker">Tonight&apos;s shelf snapshot</p>
      <div className="stores">
        {Object.entries(perChain).map(([slug, count]) => {
          const m = chainMeta[slug] ?? {};
          return (
            <div key={slug} className="store-card" style={{ "--accent": m.accent }}>
              <div className="store-name">{m.name ?? slug}</div>
              <div className="store-value">{count}</div>
              <div className="store-sub">products on tonight&apos;s shelf</div>
            </div>
          );
        })}
        {avgGap !== null && (
          <div className="store-card" style={{ "--accent": "var(--up)" }}>
            <div className="store-name">Cross-store gaps</div>
            <div className="store-value">−{avgGap}%</div>
            <div className="store-sub">avg saving on matched items</div>
          </div>
        )}
      </div>
      <p className="empty-note" style={{ padding: "10px 2px" }}>
        Inflation index activates after 72h of nightly scans — it compounds automatically.
      </p>
    </section>
  );
}

function humanize(e, chainMeta) {
  const m = e.message ?? "";
  const nameOf = (slug) => chainMeta?.[slug]?.name ?? slug;
  if (/nightly run starting/i.test(m)) return { text: "Nightly shelf scan started", level: "info" };
  if (/nightly complete|nightly run complete/i.test(m)) return { text: "Tonight's scan finished across all stores", level: "heal" };
  if (/stored (\d+) rows/.test(m)) {
    const n = m.match(/stored (\d+)/)[1];
    const chain = m.split(":")[0].trim();
    if (/0 rows/.test(m)) return null;
    return { text: `${nameOf(chain)}: ${n} products captured from the shelf`, level: "info" };
  }
  if (/drift:/i.test(m)) return { text: "A store redesigned its page — self-repair started", level: "warn" };
  if (/heal applied|recovered/i.test(m)) return { text: "Scraper repaired itself — collection resumed, same API", level: "heal" };
  if (/409|refactor|heal failed|trigger failed|no input/i.test(m)) return null;
  if (/error/i.test(e.level)) return null;
  const pretty = m.replace(/chain-[a-d]/g, nameOf);
  return { text: pretty, level: e.level };
}

function PulseCard({ events, live, chainMeta }) {
  return (
    <div className="rail-card">
      <p className="kicker" style={{ marginBottom: 4 }}>
        System pulse · {live ? "streaming" : "offline"}
      </p>
      <ul className="pulse-mini">
        {[...events].reverse()
          .map((e) => ({ ...e, h: humanize(e, chainMeta) }))
          .filter((e) => e.h && e.h.text)
          .slice(0, 10)
          .map((e, i) => (
            <li key={`${e.ts}-${i}`}>
              <span className={`lv ${e.h.level}`} />
              <div>
                <time>{new Date(e.ts).toLocaleTimeString("en-IN")}</time>
                {e.h.text}
              </div>
            </li>
          ))}
        {events.length === 0 && <li><span className="lv info" /><div>Idle — next nightly scan scheduled.</div></li>}
      </ul>
    </div>
  );
}

function InflationCard() {
  const [d, setD] = useState(null);

  useEffect(() => { api.inflation().then(setD).catch(() => {}); }, []);

  return (
    <div className="rail-card" style={{ borderTop: "3px solid var(--saffron)" }}>
      <p className="kicker">The mehngai number · month over month</p>
      {!d && <div className="empty-note" style={{ padding: 0 }}>Reading the ledger…</div>}
      {d?.status === "live" && (
        <>
          <div className="infl-num" style={{ color: d.basket_change_pct > 0 ? "var(--down)" : "var(--up)" }}>
            {d.basket_change_pct > 0 ? "+" : ""}{d.basket_change_pct}%
          </div>
          <div className="infl-sub">
            shelf prices vs {d.baseline_day} · {d.items_compared} items compared
          </div>
          <ul className="move-list" style={{ marginTop: 12 }}>
            {(d.top_movers ?? []).slice(0, 4).map((m) => (
              <li key={m.item}>
                <span className="m-name">{m.item}</span>
                <span className="m-delta" style={{ color: m.delta_pct > 0 ? "var(--down)" : "var(--up)" }}>
                  {m.delta_pct > 0 ? "+" : ""}{m.delta_pct}%
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {d?.status === "collecting" && (
        <>
          <div className="infl-num" style={{ color: "var(--muted)" }}>Day {d.scan_days}</div>
          <div className="infl-sub">
            Baseline captured on {d.latest_day}. The nightly scan compounds this into a
            month-over-month number automatically.
          </div>
          <div className="daybar">
            {[...Array(d.days_required)].map((_, i) => (
              <i key={i} style={{ background: i < d.scan_days ? "var(--saffron)" : "var(--line)" }} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function MovementsCard() { {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.movements().then(setData).catch(() => {});
  }, []);

  const sum = data?.summary;
  return (
    <div className="rail-card">
      <p className="kicker">Mehngai meter · live price moves</p>
      {sum && (
        <p style={{ margin: "0 0 10px", fontSize: "13.5px", color: "var(--muted)" }}>
          Since first scan today:{" "}
          <b style={{ color: "var(--down)" }}>{sum.up} up</b> ·{" "}
          <b style={{ color: "var(--up)" }}>{sum.down} down</b> across the shelf.
        </p>
      )}
      <ul className="move-list">
        {(data?.movements ?? []).slice(0, 6).map((mv) => (
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
          <li style={{ color: "var(--faint)" }}>Shelves steady — no moves recorded yet.</li>
        )}
      </ul>
    </div>
  );
}

function HowItWorks() {
  return (
    <div className="rail-card">
      <p className="kicker">How Mehngai works</p>
      <ul className="how" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        <li><b>1 · Collect.</b> Self-healing scrapers read real store shelves nightly via Bright Data.</li>
        <li><b>2 · Guard.</b> A watchdog validates every run; when a store redesigns its site, the scraper repairs itself — same API, zero downtime.</li>
        <li><b>3 · Compare.</b> Your basket gets priced everywhere; the radar surfaces where the same product costs less.</li>
      </ul>
    </div>
  );
}

export default function Page() {
  const [series, setSeries] = useState([]);
  const [stats, setStats] = useState({});
  const [deals, setDeals] = useState([]);
  const mergeChains = (d) => { if (d?.chains) setChainMeta((prev) => ({ ...prev, ...d.chains })); };
  const [chainMeta, setChainMeta] = useState({});
  const [pulseEvents, setPulseEvents] = useState([]);
  const [live, setLive] = useState(false);

  useEffect(() => {
    api.stats().then((d) => { setStats(d); mergeChains(d); }).catch(() => {});
    api.pulseRecent().then((d) => setPulseEvents(d.events ?? [])).catch(() => {});
  }, []);

  useEffect(
    () => openPulseStream((event) => setPulseEvents((prev) => [...prev.slice(-200), event]), setLive),
    [],
  );

  return (
    <div className="page">
      <Masthead live={live} />
      <Hero stats={stats} />
      <div className="layout">
        <main>
          <BasketBuilder chainMeta={chainMeta} onChains={mergeChains} />
          <ShelfSnapshot stats={stats} chainMeta={chainMeta} deals={deals} />
          <Deals chainMeta={chainMeta} onDeals={setDeals} onChains={mergeChains} />
        </main>
        <aside>
          <InflationCard />
          <MovementsCard />
          <HowItWorks />
          <PulseCard events={pulseEvents} live={live} chainMeta={chainMeta} />
        </aside>
      </div>
      <footer className="footer">
        <span>Mehngai · independent grocery price intelligence · built on Bright Data Scraper Studio self-healing collectors</span>
        <span>public API · /api/v1/*</span>
      </footer>
    </div>
  );
}

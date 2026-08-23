"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api, fmt, openPulseStream } from "../lib/api";
import { Sparkline } from "../components/Sparkline";

function Masthead() {
  const today = new Date().toLocaleDateString("en-IN", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });
  return (
    <>
      <header className="masthead">
        <h1>
          Mehngai<span>.</span>
        </h1>
        <div className="dateline">
          <b>{today}</b><br />
          Vol. 1 — the daily price truth
        </div>
      </header>
      <div className="tagline">
        India&apos;s independent grocery price watchdog. Real shelf prices from{" "}
        <em>real stores</em>, collected nightly by scrapers that heal themselves.
        Know what things cost — and where they cost less.
      </div>
    </>
  );
}

function BasketBuilder({ chainMeta }) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [basket, setBasket] = useState([]);
  const [result, setResult] = useState(null);
  const timer = useRef(null);

  const payload = useMemo(
    () => ({ items: basket.map((b) => ({ q: b.q, qty: b.qty })) }),
    [basket],
  );

  useEffect(() => {
    clearTimeout(timer.current);
    if (query.trim().length < 2) { setSuggestions([]); return; }
    timer.current = setTimeout(async () => {
      try {
        const d = await api.prices(query.trim());
        setSuggestions((d.results ?? []).slice(0, 6));
      } catch {}
    }, 220);
    return () => clearTimeout(timer.current);
  }, [query]);

  useEffect(() => {
    if (basket.length === 0) { setResult(null); return; }
    const t = setTimeout(async () => {
      try { setResult(await api.basketCompare(payload)); } catch {}
    }, 200);
    return () => clearTimeout(t);
  }, [payload]);

  const addItem = (item, q) => {
    setBasket((prev) => prev.some((b) => b.item === item)
      ? prev
      : [...prev, { item, q, qty: 1 }]);
    setQuery(""); setSuggestions([]);
  };
  const bump = (item, delta) => setBasket((prev) =>
    prev.map((b) => (b.item === item ? { ...b, qty: Math.max(1, Math.min(60, b.qty + delta)) } : b)));
  const remove = (item) => setBasket((prev) => prev.filter((b) => b.item !== item));

  const totals = result?.totals ?? {};
  const sortedChains = Object.entries(totals).sort((a, b) => a[1] - b[1]);
  const cheapestId = result?.cheapest_chain;
  const savingsPct = result?.savings ?? 0;

  return (
    <section id="basket">
      <div className="kicker">Your monthly basket · kitna kharcha aata hai?</div>

      <div className="searchline">
        <input
          placeholder="add items — milk, atta, detergent…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="hint">{basket.length} in basket</span>
      </div>

      {suggestions.length > 0 && (
        <ul className="suggest">
          {suggestions.map((s) => (
            <li key={s.item}>
              <button onClick={() => addItem(s.item, s.item)}>
                <span className="item-name">{s.item}</span>
                <span className="chain-tags">
                  {Object.keys(s.chains).map((c) => (
                    <span key={c} className="chain-tag"
                      style={{ borderColor: chainMeta[c]?.accent }}>
                      {(chainMeta[c]?.short ?? c)}
                    </span>
                  ))}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {basket.length > 0 && (
        <>
          <table className="ledger basket-ledger">
            <tbody>
              {basket.map((b) => (
                <tr key={b.item}>
                  <td className="item-name">{b.item}</td>
                  <td className="qty-cell">
                    <button onClick={() => bump(b.item, -1)}>−</button>
                    <span>{b.qty}</span>
                    <button onClick={() => bump(b.item, +1)}>+</button>
                  </td>
                  <td className="num">
                    {result?.items?.find((i) => i.item === b.item)?.prices &&
                      (() => {
                        const prices = result.items.find((i) => i.item === b.item).prices;
                        const entries = Object.entries(prices);
                        const min = Math.min(...entries.map(([, p]) => p.price ?? Infinity));
                        return entries.map(([c, p]) => (
                          <span key={c}
                            className={`mini-price${p.price === min ? " best-mini" : ""}`}
                            style={{ color: p.price === min ? chainMeta[c]?.accent : undefined }}>
                            {chainMeta[c]?.short}: {fmt(p.price)}
                          </span>
                        ));
                      })()}
                  </td>
                  <td className="num"><button className="x" onClick={() => remove(b.item)}>✕</button></td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className={`verdict${result ? " show" : ""}`}>
            {sortedChains.length > 0 && (
              <>
                <div className="verdict-title">Your basket, today</div>
                <div className="verdict-rows">
                  {sortedChains.map(([slug, total], idx) => (
                    <div key={slug} className={`vrow${slug === cheapestId ? " winner" : ""}`}>
                      <span className="vname" style={{ color: chainMeta[slug]?.accent }}>
                        {chainMeta[slug]?.name ?? slug}
                      </span>
                      <span className="vdots" />
                      <span className="vnum">{fmt(total)}</span>
                      {slug === cheapestId && <span className="vbadge">best</span>}
                    </div>
                  ))}
                </div>
                {savingsPct > 0 && (
                  <p className="save-line">
                    Ordering from <b style={{ color: chainMeta[cheapestId]?.accent }}>
                      {chainMeta[cheapestId]?.name}</b>{" "}
                    keeps <b>{savingsPct}%</b> of this basket in your pocket.
                  </p>
                )}
              </>
            )}
          </div>
        </>
      )}

      {basket.length === 0 && (
        <div className="empty-note">
          Build your month&apos;s essentials list — we&apos;ll price it at every store, live.
        </div>
      )}
    </section>
  );
}

function IndexStrip({ series }) {
  const blend = series.filter((p) => p.scope === "blend");
  const latest = blend[blend.length - 1];
  return (
    <section>
      <div className="kicker">The Mehngai Index · blended basket vs first collection</div>
      <div className="indexstrip">
        <div className="big-small">{latest ? latest.value.toFixed(1) : "—"}</div>
        <Sparkline points={blend} />
      </div>
    </section>
  );
}

function ChainCards({ series, chainMeta }) {
  const scopes = [...new Set(series.map((p) => p.scope))].filter((s) => s !== "blend");
  const latestBy = {};
  for (const p of series) latestBy[p.scope] = p.value;

  return (
    <section>
      <div className="kicker">Store indices · who inflated faster</div>
      <div className="chains">
        {scopes.map((scope) => {
          const m = chainMeta[scope] ?? {};
          return (
            <div key={scope} className="chain-card" style={{ borderTopColor: m.accent }}>
              <div className="name" style={{ color: m.accent }}>{m.name ?? scope}</div>
              <div className="value">{(latestBy[scope] ?? 100).toFixed(1)}</div>
              <div className="sub">vs base 100</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

const LEVEL_LABEL = { heal: "recovered", warn: "drift", error: "fault", info: "" };

function PulseRail({ events, live }) {
  return (
    <aside className="rail">
      <div className="rail-head">
        <span className={`dot${live ? "" : " off"}`} />
        System pulse · {live ? "streaming" : "offline"}
      </div>
      <ul className="pulse-list">
        {[...events].reverse().map((e, i) => (
          <li key={`${e.ts}-${i}`}>
            <span className={`lv ${e.level}`} />
            <div className="msg">
              <time>{new Date(e.ts).toLocaleTimeString("en-IN")}</time><br />
              {LEVEL_LABEL[e.level] && <b>[{LEVEL_LABEL[e.level]}] </b>}
              {e.message}
            </div>
          </li>
        ))}
        {events.length === 0 && (
          <li><span className="lv info" /><div className="msg">Waiting for the next collection…</div></li>
        )}
      </ul>
    </aside>
  );
}

function OverpricedList({ series }) {
  const [rows, setRows] = useState([]);

  useEffect(() => { api.movers(7).then((d) => setRows(d.movers ?? [])).catch(() => {}); }, []);
  void series;

  return (
    <section>
      <div className="kicker">Overpriced radar · fastest risers this week</div>
      {rows.map((m) => (
        <div key={m.scope} className="mover-row">
          <span className="ov-name" style={{ color: m.name ? undefined : "var(--text)" }}>{m.name ?? m.scope}</span>
          <div className="bar"><i style={{ width: `${Math.min(100, Math.abs(m.change_pct))}%` }} /></div>
          <span className="pct" style={{ color: m.change_pct >= 0 ? "var(--down)" : "var(--up)" }}>
            {m.change_pct >= 0 ? "+" : ""}{m.change_pct}%
          </span>
        </div>
      ))}
      {rows.length === 0 && (
        <div className="empty-note">
          Day one of tracking — the radar fills as nightly runs accumulate.
        </div>
      )}
    </section>
  );
}

export default function Page() {
  const [series, setSeries] = useState([]);
  const [pulseEvents, setPulseEvents] = useState([]);
  const [live, setLive] = useState(false);
  const [chainMeta, setChainMeta] = useState({});

  useEffect(() => {
    api.index(30).then((d) => { setSeries(d.series ?? []); setChainMeta(d.chains ?? {}); }).catch(() => {});
    api.pulseRecent().then((d) => setPulseEvents(d.events ?? [])).catch(() => {});
  }, []);

  useEffect(() => openPulseStream(
    (event) => setPulseEvents((prev) => [...prev.slice(-200), event]),
    setLive,
  ), []);

  return (
    <div className="page">
      <Masthead />
      <div className="grid">
        <main>
          <BasketBuilder chainMeta={chainMeta} />
          <IndexStrip series={series} />
          <ChainCards series={series} chainMeta={chainMeta} />
        </main>
        <div>
          <PulseRail events={pulseEvents} live={live} />
          <OverpricedList series={series} />
        </div>
      </div>
      <footer className="footer">
        <span>Mehngai — powered by Bright Data Scraper Studio self-healing collectors.</span>
        <span>public API · /api/v1/*</span>
      </footer>
    </div>
  );
}

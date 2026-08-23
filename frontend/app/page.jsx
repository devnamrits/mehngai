"use client";

import { useEffect, useRef, useState } from "react";
import { api, fmt, openPulseStream } from "../lib/api";
import { Sparkline } from "../components/Sparkline";

function Masthead() {
  const today = new Date().toLocaleDateString("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  return (
    <>
      <header className="masthead">
        <h1>
          Mehngai<span>.</span>
        </h1>
        <div className="dateline">
          <b>{today}</b>
          <br />
          Vol. 1 — the daily price truth
        </div>
      </header>
      <div className="tagline">
        An independent cost-of-living index computed nightly from real shelf prices by{" "}
        <em>self-healing scrapers</em> that refuse to die. No officials consulted.
      </div>
    </>
  );
}

function IndexHero({ series }) {
  const blend = series.filter((p) => p.scope === "blend");
  const latest = blend[blend.length - 1];
  const prev = blend.length > 1 ? blend[blend.length - 2] : null;
  const delta = latest && prev ? ((latest.value / prev.value - 1) * 100).toFixed(2) : null;
  const dir = delta === null ? "flat" : Number(delta) > 0 ? "up" : Number(delta) < 0 ? "down" : "flat";

  return (
    <section>
      <div className="kicker">The Mehngai Index · blended basket</div>
      <div className="hero">
        <div>
          <div className="big">
            {latest ? latest.value.toFixed(1) : "—"}
            <small>base 100</small>
          </div>
          {delta !== null && (
            <span className={`delta ${dir}`}>
              {dir === "up" ? "▲" : dir === "down" ? "▼" : "■"} {Math.abs(delta)}% vs last run
              {dir === "up" && " — your basket got pricier"}
              {dir === "down" && " — relief, briefly"}
            </span>
          )}
        </div>
        <Sparkline points={blend} />
      </div>
    </section>
  );
}

function ChainStrip({ series }) {
  const scopes = [...new Set(series.map((p) => p.scope))].filter((s) => s !== "blend");
  const latestBy = {};
  for (const p of series) latestBy[p.scope] = p.value;
  const cheapest = scopes.slice().sort((a, b) => latestBy[a] - latestBy[b])[0];

  return (
    <section>
      <div className="kicker">Chain indices</div>
      <div className="chains">
        {scopes.map((scope) => (
          <div key={scope} className={`chain-card${scope === cheapest && scopes.length > 1 ? " best" : ""}`}>
            <div className="name">{scope.replace("chain-", "")}</div>
            <div className="value">{(latestBy[scope] ?? 100).toFixed(1)}</div>
            <div className="sub">vs base 100</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function Explorer() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searched, setSearched] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    clearTimeout(timer.current);
    if (query.trim().length < 2) {
      setResults([]);
      setSearched(false);
      return;
    }
    timer.current = setTimeout(async () => {
      try {
        const data = await api.prices(query.trim());
        setResults(data.results ?? []);
        setSearched(true);
      } catch {
        /* keep old results on failure */
      }
    }, 250);
    return () => clearTimeout(timer.current);
  }, [query]);

  return (
    <section>
      <div className="kicker">Price explorer · what does it cost where?</div>
      <div className="searchline">
        <input
          autoFocus
          placeholder="milk, atta, detergent…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="hint">type ≥ 2 letters</span>
      </div>

      {searched && results.length === 0 && (
        <div className="empty-note">Nothing on the shelves matches “{query}”. Yet.</div>
      )}

      {results.length > 0 && (
        <table className="ledger">
          <thead>
            <tr>
              <th>Item</th>
              {Object.keys(results[0].chains).map((c) => (
                <th key={c} className="num">
                  {c.replace("chain-", "")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {results.map((r) => {
              const entries = Object.entries(r.chains);
              const min = Math.min(...entries.map(([, v]) => v.price ?? Infinity));
              return (
                <tr key={r.item}>
                  <td className="item-name">{r.item}</td>
                  {entries.map(([chain, v]) => (
                    <td key={chain} className={`num${v.price === min ? " best-cell" : ""}`}>
                      {v.price === min ? "◆ " : ""}
                      {fmt(v.price)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Movers({ windowDays }) {
  const [movers, setMovers] = useState([]);

  useEffect(() => {
    api
      .movers(windowDays)
      .then((d) => setMovers(d.movers ?? []))
      .catch(() => {});
  }, [windowDays]);

  const maxAbs = Math.max(...movers.map((m) => Math.abs(m.change_pct)), 1);

  return (
    <section>
      <div className="kicker">Movers · last {windowDays} days</div>
      {movers.map((m) => (
        <div key={m.scope} className="mover-row">
          <span>{m.scope.replace("chain-", "")}</span>
          <div className="bar">
            <i style={{ width: `${(Math.abs(m.change_pct) / maxAbs) * 100}%` }} />
          </div>
          <span className="pct" style={{ color: m.change_pct >= 0 ? "var(--down)" : "var(--up)" }}>
            {m.change_pct >= 0 ? "+" : ""}
            {m.change_pct}%
          </span>
        </div>
      ))}
      {movers.length === 0 && <div className="empty-note">Not enough history yet.</div>}
    </section>
  );
}

function Briefing() {
  const [brief, setBrief] = useState(null);

  useEffect(() => {
    api
      .briefing()
      .then(setBrief)
      .catch(() => {});
  }, []);

  if (!brief) return null;
  return (
    <section>
      <div className="kicker">Today’s briefing</div>
      <div className="briefing">{brief.narrative}</div>
      <div className="source-tag">source: {brief.source}</div>
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
              <time>{new Date(e.ts).toLocaleTimeString("en-IN")}</time>
              <br />
              {LEVEL_LABEL[e.level] && <b>[{LEVEL_LABEL[e.level]}] </b>}
              {e.message}
            </div>
          </li>
        ))}
        {events.length === 0 && (
          <li>
            <span className="lv info" />
            <div className="msg">Waiting for the next collection…</div>
          </li>
        )}
      </ul>
    </aside>
  );
}

export default function Page() {
  const [series, setSeries] = useState([]);
  const [pulseEvents, setPulseEvents] = useState([]);
  const [live, setLive] = useState(false);

  useEffect(() => {
    api
      .index(30)
      .then((d) => setSeries(d.series ?? []))
      .catch(() => {});

    api
      .pulseRecent()
      .then((d) => setPulseEvents(d.events ?? []))
      .catch(() => {});
  }, []);

  useEffect(
    () =>
      openPulseStream(
        (event) => setPulseEvents((prev) => [...prev.slice(-200), event]),
        setLive,
      ),
    [],
  );

  return (
    <div className="page">
      <Masthead />
      <div className="grid">
        <main>
          <IndexHero series={series} />
          <ChainStrip series={series} />
          <Explorer />
          <Briefing />
        </main>
        <div>
          <PulseRail events={pulseEvents} live={live} />
          <Movers windowDays={7} />
        </div>
      </div>
      <footer className="footer">
        <span>Mehngai — built with Bright Data Scraper Studio self-healing collectors.</span>
        <span>public API · /api/v1/*</span>
      </footer>
    </div>
  );
}

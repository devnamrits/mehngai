# Mehngai — Product Explained

> A newspaper-style dashboard that tells you **how much more expensive everyday life got today**, computed independently from real supermarket shelf prices, kept alive by scrapers that repair themselves.

## The daily machine

```
cron fires → trigger collectors on Bright Data → JSON rows come back
→ validators inspect rows for anomalies → if broken: auto-heal, re-run
→ normalize prices to ₹/kg · ₹/L → resolve same items across chains
→ compute today's index number → store → briefing generated → alerts sent
```

Everything on the dashboard is the readable surface of this pipeline.

## Vocabulary

### Chain
A supermarket retailer we track ("data source" in plain words). One Scraper Studio collector per chain. Chain names are configuration, not code.

### Base 100
The index convention statisticians use. The **first collection day becomes 100**; every later number reads *"same basket, what % cost now?"*. An index of **113.5** means the identical basket that cost ₹1,000 on day one costs **₹1,135 today**. Deliberately relative — it measures change, exactly like official CPI.

### Chain indices
The same basket tracked **per retailer**. If chain-a sits at 110 while chain-c sits at 118, chain-c inflated faster. The saffron-highlighted card marks the currently cheapest chain.

### Blended basket
The average across chains — one glanceable headline number ("the India view"), with per-chain cards beneath for detail. Macro lens + micro lens.

### How the math works (chained index)
1. Every item is normalized to a **unit price**: ₹/kg solids, ₹/L liquids — so Amul 500ml @ ₹33 and Amul 1L @ ₹66 compete fairly.
2. Per item we take today's **median unit price** across listings (median, because one mis-scraped ₹9,900 "milk" cannot poison the number).
3. Today's index = **yesterday's index × (today's basket ÷ yesterday's basket)**, chained day over day, with day-one prices frozen as reference weights. Method string: `chained-laspeyres`.

### Movers
Leaderboard of which chain's prices changed fastest over the last N days (default 7) — "who is squeezing me this week?". Red ▲ = getting expensive (bad for you), green ▼ = relief.

### Price explorer
Type any item → ledger of what each chain charges today, ◆ marking the cheapest. The daily-usefulness feature; everything else is context around it.

### System Pulse
The watchdog's public diary. Every collection emits events:

| Level | Meaning |
|---|---|
| info | stored N rows |
| warn / drift | something looked wrong (empty run, null ratio spike, schema drift, price outliers) |
| heal | auto-repaired via `bdata scraper heal` flow — same Collector ID, zero downtime |
| error | unresolved fault |

Most projects hide scraper ops; Mehngai streams them into the product, because "never goes down" should be provable, not claimed. Incident receipts are also persisted (`incidents` table).

### Briefing
AI-generated summary built strictly from verified facts (index levels, deltas, movers, open incidents). With `AI_BASE_URL` set it runs through any OpenAI-compatible LLM (Ollama locally, DGX Spark later); without it, a deterministic template writes the same briefing — the feature never breaks and costs nothing.

## Why this design

| Feature | Judging criterion it serves |
|---|---|
| Base-100 chained index | Technical excellence |
| Movers + explorer | Impact — usable daily by real people |
| Pulse rail + incident receipts | Reliability & self-healing (the sponsor's core ask) |
| Blended vs per-chain split | Creativity — macro lens + micro lens |


## The product surface (final)

### Your Monthly Basket (the hero)
Search or tap category chips → items land in your basket with quantity steppers.
Mehngai prices the whole list at every store using tonight's real shelves and
renders a verdict: per-store totals, the winner, and the exact rupees saved by
ordering from the right place.

### Smarter Pick Radar
Finds the *same* product stocked at multiple stores and ranks the biggest
percentage gaps — "tomato: ₹27.50 at Nature's Basket vs ₹100 at Spencer's,
pay 72% less." Every card is a receipt-backed comparison.

### Store inflation index
Chained base-100 index per retailer (and blended), compounding nightly as the
cron fires — the macro lens over the micro comparisons.

### System pulse
The watchdog's public diary: collection events, drift detections, autonomous
heals. Reliability is streamed into the product instead of being claimed in a slide.

## UX principles applied

- **One primary job per screen** — basket building dominates; everything else supports it.
- **Recognition over recall** — category chips (`+ milk`, `+ atta`) before typing.
- **Immediate feedback** — debounced suggestions, live totals on every quantity change.
- **Honest empty states** — if data isn't there yet, we say so; we never invent numbers.
- **Retailer identity** — real names and brand accents everywhere; no anonymous chain-a/b labels.


## Category clusters (the full common-man basket)

The Mehngai Number is a median across consumer-category clusters — each cluster
is its own mini-index with an honest lifecycle (baseline → live after 2nd scan):

| Cluster | Status | Source type |
|---|---|---|
| Groceries | live · 4 stores · 333 items | Scraper Studio Discovery/PDP collectors |
| Fuel & commute (petrol/diesel/LPG) | baseline today | Commodity table collector |
| Gold & Silver | 9-day window · +5.28% | Commodity history collector |
| Electronics & big-ticket | connector designed (Apple/Croma) | roadmap |
| Travel & airfare | connector designed (weekly true-fare scans) | roadmap |
| Rent & school fees | connector designed (listing/fee-page scrapes) | roadmap |

**Why weekly:** retail discounts are noise, not inflation. Weekly medians keep
the indicator on true prices. **Why medians:** a single mis-scraped ₹9,900
"milk" cannot move the index.

**Gold's honest role:** a savings-benchmark cluster — the index leads with
consumer essentials; gold sits beside them as context, never as the headline.

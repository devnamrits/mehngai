# Agent rules — Mehngai

## Project
Live cost-of-living index built on Bright Data Scraper Studio self-healing collectors.
Read SPEC.md before changing anything. Compliance rules in SPEC.md §4 are non-negotiable.

## Scraper Studio usage (terminal-first, never rebuild)

Collectors are pinned below. NEVER call `bdata scraper create` for these targets again —
always run the existing collector:

- Chain A: `$COLLECTOR_CHAIN_A`
- Chain B: `$COLLECTOR_CHAIN_B`
- Chain C: `$COLLECTOR_CHAIN_C`

Run:
```bash
bdata scraper run $COLLECTOR_CHAIN_A <url> --pretty
```

If a collector returns empty/null fields (site changed), heal it — same Collector ID,
downstream untouched:
```bash
bdata scraper heal $COLLECTOR_CHAIN_A "<field-level description of what broke>" \
  --url <url>
bdata scraper approve $COLLECTOR_CHAIN_A --url <url>   # review first!
```
`--auto-approve` is reserved for the automated watchdog after one supervised approval.

Auth is headless: export BRIGHTDATA_API_KEY from .env; never run `bdata login`.

## Hard rules
- Public pages only; no login/paywall/personal data; NO government websites.
- Never commit .env or real keys; mask them in any demo material.
- Every heal incident must append an entry to incidents/ ledger.

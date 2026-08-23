DEFAULT_CHAIN_META = {
    "chain-a": {"name": "Nature's Basket", "short": "NB", "accent": "#7bc96f"},
    "chain-b": {"name": "DMart Ready", "short": "DM", "accent": "#ff8c42"},
    "chain-c": {"name": "Spencer's", "short": "SP", "accent": "#5ec8d8"},
    "chain-d": {"name": "Modern Bazaar", "short": "MB", "accent": "#e8a0bf"},
}


def chain_meta(chain_slug: str, overrides: dict | None = None) -> dict:
    meta = dict(DEFAULT_CHAIN_META.get(chain_slug, {}))
    if overrides and chain_slug in overrides:
        meta.update(overrides[chain_slug])
    meta.setdefault("name", chain_slug.replace("chain-", "").upper())
    meta.setdefault("short", chain_slug[-2:].upper())
    meta.setdefault("accent", "#ffb020")
    return meta


def parse_chain_names(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    out = {}
    for pair in raw.split("|"):
        if "=" in pair:
            slug, name = pair.split("=", 1)
            out[slug.strip()] = name.strip()
    return out

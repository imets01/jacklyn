"""Asset profiles (fund issuer, TER, sector, ...) and logos, fetched in the background and cached in the DB.

Logos are downloaded by the server, never by browsers: the strict CSP stays intact, each image is fetched
once and cached, and nobody's browser tells a third party which securities they hold. Elbstream (by ISIN,
plus commodity, crypto and currency tiles) is tried first, then Google's favicon service by website.
"""

import datetime as dt
import logging
import re
import struct
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from app.enums import AssetClass
from app.models import Asset, AssetLogo, AssetProfile

logger = logging.getLogger(__name__)

PROFILE_MAX_AGE = dt.timedelta(days=30)
LOGO_MAX_AGE = dt.timedelta(days=90)
LOGO_MISS_RETRY = dt.timedelta(days=7)
MAX_LOGO_BYTES = 256 * 1024
MIN_LOGO_PIXELS = 32  # smaller favicons look blurry in an avatar; initials look better


@dataclass(frozen=True)
class Provider:
    name: str
    domain: str
    pattern: re.Pattern[str]


def _provider(name: str, domain: str, pattern: str) -> Provider:
    return Provider(name, domain, re.compile(pattern, re.IGNORECASE))


# Fund issuers, matched against the fund name and Yahoo's fundFamily. Order matters: brands before parents.
PROVIDERS: tuple[Provider, ...] = (
    _provider("iShares", "ishares.com", r"\bishares\b|\bblackrock\b|\bishs\b"),
    _provider("Vanguard", "vanguard.com", r"\bvanguard\b"),
    _provider("Xtrackers", "xtrackers.com", r"\bxtrackers\b|\bdb x-trackers\b|\bdws\b"),
    _provider("Amundi", "amundi.com", r"\bamundi\b|\blyxor\b"),
    _provider("SPDR", "ssga.com", r"\bspdr\b|\bstate street\b"),
    _provider("Invesco", "invesco.com", r"\binvesco\b"),
    _provider("WisdomTree", "wisdomtree.com", r"\bwisdomtree\b"),
    _provider("VanEck", "vaneck.com", r"\bvaneck\b|\bvan eck\b"),
    _provider("Global X", "globalxetfs.com", r"\bglobal x\b"),
    _provider("L&G", "lgim.com", r"\bl&g\b|\blegal (&|and) general\b"),
    _provider("UBS", "ubs.com", r"\bubs\b"),
    _provider("HSBC", "hsbc.com", r"\bhsbc\b"),
    _provider("J.P. Morgan", "jpmorgan.com", r"\bj\.?\s?p\.?\s?morgan\b|\bjpm\b"),
    _provider("Fidelity", "fidelity.com", r"\bfidelity\b"),
    _provider("Franklin Templeton", "franklintempleton.com", r"\bfranklin\b"),
    _provider("Schwab", "schwab.com", r"\bschwab\b"),
    _provider("First Trust", "ftportfolios.com", r"\bfirst trust\b"),
    _provider("ARK Invest", "ark-funds.com", r"\bark\b.*\betf\b"),
    _provider("BNP Paribas", "bnpparibas.com", r"\bbnp\b"),
    _provider("Deka", "deka.de", r"\bdeka\b"),
)

_METALS = r"(gold|silver|platinum|palladium|precious metals?)"
_COMMODITY = re.compile(
    rf"\bphysical\b.*\b{_METALS}\b|\b{_METALS}\b.*\b(etc|etp|bullion)\b|\bxetra-gold\b|\bgold bullion\b",
    re.IGNORECASE,
)
_FUND_WORDS = re.compile(r"\b(etf|ucits)\b", re.IGNORECASE)
_MUTUAL_FUND_WORDS = re.compile(r"\b(fund|fonds|alap|sicav|ucits|oeic|index)\b", re.IGNORECASE)


def detect_provider(*texts: str | None) -> Provider | None:
    for provider in PROVIDERS:
        if any(text and provider.pattern.search(text) for text in texts):
            return provider
    return None


def is_commodity(name: str | None) -> bool:
    return bool(name and _COMMODITY.search(name))


def website_domain(url: str | None) -> str | None:
    if not url:
        return None
    host = urlsplit(url if "://" in url else f"https://{url}").hostname or ""
    host = host.lower().removeprefix("www.")
    # A registrable host name only: no IP addresses, no single-label intranet names.
    return host if re.fullmatch(r"([a-z0-9-]+\.)+[a-z]{2,}", host) else None


def crypto_code(asset: Asset) -> str | None:
    """BTC from BTC, BTC-USD or BTC-EUR."""
    code = (asset.yf_ticker or asset.symbol).split("-")[0].lower()
    return code if re.fullmatch(r"[a-z0-9]{2,10}", code) else None


def logo_candidates(asset: Asset, profile: AssetProfile) -> list[str]:
    """Logo keys to try, best first. The UI draws metals and initials when none of them has an image.

    Elbstream by ISIN comes first (round, brand-colored marks for stocks and fund issuers alike), then the
    company's or fund issuer's website icon.
    """
    if asset.asset_class is AssetClass.COMMODITY:
        metal = commodity_key(profile.long_name or asset.name)
        return [f"commodity:{metal}"] if metal else []
    if asset.asset_class is AssetClass.CRYPTO:
        code = crypto_code(asset)
        return [f"crypto:{code}"] if code else []
    keys = []
    if asset.isin and ISIN_RE.fullmatch(asset.isin):
        keys.append(f"isin:{asset.isin}")
    elif asset.currency == "USD" and re.fullmatch(r"[A-Z]{1,5}", asset.symbol):
        keys.append(f"symbol:{asset.symbol}")  # US tickers are unambiguous enough without an ISIN
    if asset.asset_class in (AssetClass.ETF, AssetClass.FUND):
        provider = detect_provider(profile.provider, profile.long_name, asset.name)
        domain = provider.domain if provider else None
    else:
        domain = website_domain(profile.website)
    if domain:
        keys.append(f"domain:{domain}")
    return keys


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() and number >= 0 else None


def _text(value: Any, limit: int) -> str | None:
    return (value.strip()[:limit] or None) if isinstance(value, str) else None


def apply_info(asset: Asset, profile: AssetProfile, info: dict[str, Any]) -> None:
    """Copy what Yahoo's `info` knows onto the profile, and correct the asset's name and class."""
    profile.quote_type = _text(info.get("quoteType"), 32)
    profile.long_name = _text(info.get("longName") or info.get("shortName"), 200)
    profile.sector = _text(info.get("sector"), 120)
    profile.industry = _text(info.get("industry"), 120)
    profile.description = _text(info.get("longBusinessSummary"), 4000)
    profile.website = _text(info.get("website"), 200)
    profile.country = _text(info.get("country"), 64)
    # Yahoo reports netExpenseRatio in percent (0.07 = 0.07%); store a plain fraction.
    ter = _decimal(info.get("netExpenseRatio"))
    profile.expense_ratio = ter / 100 if ter is not None else None
    profile.fund_size = _decimal(info.get("totalAssets"))
    family = _text(info.get("fundFamily"), 200)
    provider = detect_provider(family, profile.long_name, asset.name)
    profile.provider = provider.name if provider else (family[:80] if family else None)
    classify(asset, profile)


def _class_from_quote_type(profile: AssetProfile, name: str | None) -> AssetClass | None:
    match profile.quote_type:
        case "ETF":
            return AssetClass.ETF
        case "CRYPTOCURRENCY":
            return AssetClass.CRYPTO
        case "MUTUALFUND" if _MUTUAL_FUND_WORDS.search(name or ""):
            # Yahoo tags some Budapest shares (Richter, Magyar Telekom) MUTUALFUND; trust it only for fund names.
            return AssetClass.FUND
        case _:
            return None


def classify(asset: Asset, profile: AssetProfile) -> None:
    if not asset.name and profile.long_name:
        asset.name = profile.long_name
    name = profile.long_name or asset.name
    if is_commodity(name):
        asset.asset_class = AssetClass.COMMODITY
    elif asset.asset_class in (AssetClass.STOCK, AssetClass.OTHER) and (
        better := _class_from_quote_type(profile, name)
    ):
        asset.asset_class = better
    elif asset.asset_class is AssetClass.STOCK and detect_provider(name) and _FUND_WORDS.search(name or ""):
        asset.asset_class = AssetClass.ETF
    if not profile.provider and asset.asset_class in (AssetClass.ETF, AssetClass.FUND, AssetClass.COMMODITY):
        provider = detect_provider(name)
        profile.provider = provider.name if provider else None


def fetch_info(ticker: str) -> dict[str, Any]:
    from app.services.market_data import load_yfinance  # noqa: PLC0415 - avoid an import cycle

    info = load_yfinance().Ticker(ticker).info
    return info if isinstance(info, dict) else {}


FUND_CLASS_KEYS = {
    "stockPosition": "stock",
    "bondPosition": "bond",
    "cashPosition": "cash",
    "preferredPosition": "other",
    "convertiblePosition": "other",
    "otherPosition": "other",
}


def _weights(raw: dict[str, Any] | None, keys: dict[str, str] | None = None) -> dict[str, str] | None:
    """{name: fraction} as decimal strings, dropping zeros and anything that isn't a sane fraction."""
    if not raw:
        return None
    weights: dict[str, Decimal] = {}
    for name, value in raw.items():
        fraction = _decimal(value)
        if fraction is None or fraction == 0 or fraction > 1:
            continue
        key = keys.get(str(name), "other") if keys else str(name)
        weights[key] = weights.get(key, Decimal(0)) + fraction
    return {key: str(value.quantize(Decimal("0.0001"))) for key, value in weights.items()} or None


def fetch_fund_data(ticker: str) -> dict[str, dict[str, str] | None]:
    """Sector, asset-class and top-10 weights of a fund from Yahoo; any part may be missing."""
    from app.services.market_data import load_yfinance  # noqa: PLC0415 - avoid an import cycle

    funds = load_yfinance().Ticker(ticker).funds_data
    top = getattr(funds, "top_holdings", None)
    top_weights: dict[str, Any] = {}
    names: dict[str, str] = {}
    if top is not None and not top.empty and "Holding Percent" in top:
        top_weights = {str(symbol): value for symbol, value in top["Holding Percent"].items()}
        if "Name" in top:
            names = {str(symbol): str(name)[:120] for symbol, name in top["Name"].items() if isinstance(name, str)}
    return {
        "sectors": _weights(getattr(funds, "sector_weightings", None)),
        "classes": _weights(getattr(funds, "asset_classes", None), FUND_CLASS_KEYS),
        "top": _weights(top_weights),
        "names": names or None,
    }


def apply_fund_data(profile: AssetProfile, data: dict[str, dict[str, str] | None]) -> None:
    profile.sector_weights = data.get("sectors")
    profile.class_weights = data.get("classes")
    profile.top_holdings = data.get("top")
    profile.holding_names = {**(profile.holding_names or {}), **(data.get("names") or {})} or None


def profile_is_stale(profile: AssetProfile | None, now: dt.datetime) -> bool:
    return profile is None or now - profile.fetched_at > PROFILE_MAX_AGE


def _as_strings(weights: dict[str, Decimal] | None) -> dict[str, str] | None:
    return {key: str(value.quantize(Decimal("0.000001"))) for key, value in weights.items()} if weights else None


def apply_eulerpool(profile: AssetProfile, isin: str, token: str) -> None:
    from app.services.eulerpool import fetch_fund  # noqa: PLC0415 - optional provider

    look_through = fetch_fund(isin, token)
    profile.country_weights = _as_strings(look_through.countries)
    profile.holdings = _as_strings(look_through.holdings)
    if look_through.names:
        profile.holding_names = {**(profile.holding_names or {}), **look_through.names}


def refresh_profile(
    session: Session, asset: Asset, *, use_network: bool, eulerpool_token: str | None = None
) -> AssetProfile:
    profile = session.get(AssetProfile, asset.id) or AssetProfile(asset_id=asset.id)
    if use_network and asset.yf_ticker:
        try:
            apply_info(asset, profile, fetch_info(asset.yf_ticker))
        except Exception as exc:  # noqa: BLE001 - provider hiccups just leave the profile name-based
            logger.info("No profile for %s: %s", asset.yf_ticker, exc)
            classify(asset, profile)
        if asset.asset_class in (AssetClass.ETF, AssetClass.FUND):
            try:
                apply_fund_data(profile, fetch_fund_data(asset.yf_ticker))
            except Exception as exc:  # noqa: BLE001 - look-through is optional
                logger.info("No fund data for %s: %s", asset.yf_ticker, exc)
    else:
        classify(asset, profile)
    if use_network and eulerpool_token and asset.isin:
        try:
            if asset.asset_class in (AssetClass.ETF, AssetClass.FUND):
                apply_eulerpool(profile, asset.isin, eulerpool_token)
            elif asset.asset_class is AssetClass.STOCK and not profile.country:
                from app.services.eulerpool import fetch_company_country  # noqa: PLC0415 - optional provider

                profile.country = fetch_company_country(asset.isin, eulerpool_token)
        except Exception as exc:  # noqa: BLE001 - keep the previous data when the provider fails
            logger.info("No Eulerpool data for %s: %s", asset.isin, type(exc).__name__)
    profile.fetched_at = dt.datetime.now(dt.UTC)
    session.add(profile)
    return profile


# ------------------------------------------------------------------------------------------------ logos


ELBSTREAM = "https://api.elbstream.com/logos"
ISIN_RE = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")
# Elbstream's commodity tiles, keyed by the identifier its API accepts.
COMMODITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (key, re.compile(pattern, re.IGNORECASE))
    for key, pattern in (
        ("gold", r"\bgold\b"),
        ("silver", r"\bsilver\b"),
        ("platinum", r"\bplatinum\b"),
        ("palladium", r"\bpalladium\b"),
        ("copper", r"\bcopper\b"),
        ("natural_gas", r"\bnatural gas\b"),
        ("oil", r"\b(crude|brent|wti|oil)\b"),
    )
)
# Shapes and paint only: anything that can run script, load a URL or embed a document is refused.
SVG_ELEMENTS = frozenset(
    {
        "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "defs", "clipPath",
        "mask", "linearGradient", "radialGradient", "stop", "title", "desc",
        "filter", "feBlend", "feFlood", "feGaussianBlur", "feOffset", "feColorMatrix", "feComposite",
        "feMerge", "feMergeNode",
    }
)  # fmt: skip
SVG_ATTRIBUTE_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9:\-]*")
SVG_URL_RE = re.compile(r"url\(\s*([^)]*)\)", re.IGNORECASE)


def commodity_key(name: str | None) -> str | None:
    for key, pattern in COMMODITY_PATTERNS:
        if name and pattern.search(name):
            return key
    return None


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def safe_svg(data: bytes) -> bool:
    """True for a plain vector drawing: allow-listed elements, no event handlers, links or external URLs."""
    from defusedxml import ElementTree  # noqa: PLC0415 - only needed for SVG logos

    try:
        root = ElementTree.fromstring(data)
    except Exception:  # noqa: BLE001 - malformed or hostile XML is simply not a logo
        return False
    if _local(root.tag) != "svg":
        return False
    for element in root.iter():
        if not isinstance(element.tag, str) or _local(element.tag) not in SVG_ELEMENTS:
            return False
        for raw_name, value in element.attrib.items():
            name = _local(raw_name)
            if not SVG_ATTRIBUTE_RE.fullmatch(name) or name.lower().startswith("on") or name in {"href", "src"}:
                return False
            if any(not ref.strip(" '\"").startswith("#") for ref in SVG_URL_RE.findall(value)):
                return False
            if "javascript:" in value.lower() or "@import" in value.lower():
                return False
    return True


def image_type(data: bytes) -> str | None:
    """Content type for the formats we accept: rasters, and SVG only when `safe_svg` passes."""
    head = data[:256].lstrip()
    if head.startswith((b"<svg", b"<?xml")):
        return "image/svg+xml" if safe_svg(data) else None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] == b"\x00\x00\x01\x00":
        return "image/x-icon"
    return None


def png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or not data.startswith(b"\x89PNG"):
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def usable_logo(data: bytes) -> str | None:
    if not data or len(data) > MAX_LOGO_BYTES:
        return None
    kind = image_type(data)
    if kind == "image/png" and (size := png_size(data)) and min(size) < MIN_LOGO_PIXELS:
        return None
    return kind


def logo_sources(key: str) -> list[tuple[str, str]]:
    """(source name, URL) candidates in order of preference. Hosts are fixed: no user-controlled URLs."""
    kind, _, value = key.partition(":")
    match kind:
        case "isin":
            return [("elbstream", f"{ELBSTREAM}/isin/{value}")]
        case "symbol":
            return [("elbstream", f"{ELBSTREAM}/symbol/{value}")]
        case "commodity":
            return [("elbstream", f"{ELBSTREAM}/commodity/{value}?size=128")]
        case "currency":
            return [("elbstream", f"{ELBSTREAM}/currency/{value}")]
        case "country":
            return [("elbstream", f"{ELBSTREAM}/country/{value}")]
        case "crypto":
            return [
                ("elbstream", f"{ELBSTREAM}/crypto/{value}"),
                (
                    "cryptocurrency-icons",
                    f"https://cdn.jsdelivr.net/npm/cryptocurrency-icons@0.18.1/128/color/{value}.png",
                ),
            ]
        case "domain":
            return [("google", f"https://www.google.com/s2/favicons?domain={value}&sz=128")]
        case _:
            return []


def download_logo(client: httpx.Client, key: str) -> tuple[bytes, str, str] | None:
    for source, url in logo_sources(key):
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            logger.info("Logo source %s failed for %s: %s", source, key, type(exc).__name__)
            continue
        if response.status_code != 200:
            continue
        data = response.content
        if kind := usable_logo(data):
            return data, kind, source
    return None


def logo_is_due(logo: AssetLogo | None, now: dt.datetime) -> bool:
    if logo is None:
        return True
    return now - logo.fetched_at > (LOGO_MAX_AGE if logo.data else LOGO_MISS_RETRY)


def refresh_logos(
    session: Session,
    keys: set[str],
    *,
    limit: int = 30,
    transport: httpx.BaseTransport | None = None,
) -> int:
    """Fetch logos that are missing or due; returns how many images were stored."""
    return resolve_logos(session, {i: [key] for i, key in enumerate(sorted(keys))}, limit=limit, transport=transport)[1]


def _fetch_into(client: httpx.Client, key: str, logo: AssetLogo | None, now: dt.datetime) -> tuple[AssetLogo, bool]:
    found = download_logo(client, key)
    logo = logo or AssetLogo(key=key)
    if found:
        logo.data, logo.content_type, logo.source = found
    elif logo.data is None:
        logo.content_type = logo.source = None  # a miss; a previously good image is kept
    logo.fetched_at = now
    return logo, found is not None


def resolve_logos(
    session: Session,
    candidates: dict[int, list[str]],
    *,
    limit: int = 30,
    transport: httpx.BaseTransport | None = None,
) -> tuple[dict[int, str | None], int]:
    """For each owner, the first candidate key that has an image, fetching due candidates in order.

    Returns ({owner: chosen key}, images stored). At most `limit` downloads happen per call; candidates
    not fetched yet are skipped this time, so a lower-priority logo may stand in until the next refresh.
    """
    now = dt.datetime.now(dt.UTC)
    all_keys = {key for keys in candidates.values() for key in keys}
    existing = (
        {logo.key: logo for logo in session.scalars(select(AssetLogo).where(AssetLogo.key.in_(all_keys)))}
        if all_keys
        else {}
    )
    chosen: dict[int, str | None] = {}
    stored = budget = 0
    headers = {"User-Agent": "Jacklyn/1.0 (self-hosted portfolio tracker)"}
    with httpx.Client(timeout=8, follow_redirects=True, headers=headers, transport=transport) as client:
        for owner, keys in candidates.items():
            chosen[owner] = None
            for key in keys:
                logo = existing.get(key)
                if logo_is_due(logo, now) and budget < limit:
                    budget += 1
                    logo, fetched = _fetch_into(client, key, logo, now)
                    existing[key] = logo
                    session.add(logo)
                    stored += fetched
                if logo is not None and logo.data is not None:
                    chosen[owner] = key
                    break
    session.flush()
    return chosen, stored


def shared_logo_urls(session: Session, condition: ColumnElement[bool]) -> dict[str, str]:
    """Cache-busting `/api/logos/{key}` URLs for downloaded flags and currency badges matching `condition`."""
    rows = session.execute(
        select(AssetLogo.key, AssetLogo.fetched_at).where(condition, AssetLogo.data.is_not(None))
    ).all()
    return {key: f"/api/logos/{key}?v={int(fetched.timestamp())}" for key, fetched in rows}

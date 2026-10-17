"""Fund look-through from Eulerpool: the real country mix and full holdings of an ETF, by ISIN.

Optional: used only when JACKLYN_EULERPOOL_TOKEN is set. The free plan allows 100k requests a month;
Jacklyn needs two per fund per profile refresh (every 30 days). Called server-side only, and the key
travels in a header, so it never ends up in logs or URLs.
"""

import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

logger = logging.getLogger(__name__)
BASE_URL = "https://api.eulerpool.com/api/1"
MAX_HOLDINGS = 5000  # every holding of even an all-world fund (VWCE has ~3,800), so overlaps are exact
_ISIN = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")
_PERCENT = Decimal(100)
# Eulerpool uses ISO 3166 short names; Jacklyn (and Yahoo, and the benchmark file) use common ones.
COUNTRY_NAMES = {
    "United Kingdom of Great Britain and Northern Ireland": "United Kingdom",
    "United States of America": "United States",
    "Korea (the Republic of)": "South Korea",
    "Korea": "South Korea",
    "Korea, Republic of": "South Korea",
    "Taiwan (Province of China)": "Taiwan",
    "Netherlands (Kingdom of the)": "Netherlands",
    "Russian Federation (the)": "Russia",
    "Russian Federation": "Russia",
    "Viet Nam": "Vietnam",
    "Türkiye": "Turkey",
    "Iran (Islamic Republic of)": "Iran",
    "Czechia": "Czech Republic",
    "Hong Kong SAR": "Hong Kong",
}
OTHER = "Other"
# Company profiles report ISO 3166 alpha-2 codes.
ISO_COUNTRIES = {
    "US": "United States", "CA": "Canada", "GB": "United Kingdom", "IE": "Ireland", "CH": "Switzerland",
    "LI": "Liechtenstein", "DE": "Germany", "AT": "Austria", "FR": "France", "NL": "Netherlands", "BE": "Belgium",
    "LU": "Luxembourg", "IT": "Italy", "ES": "Spain", "PT": "Portugal", "DK": "Denmark", "SE": "Sweden",
    "NO": "Norway", "FI": "Finland", "PL": "Poland", "CZ": "Czech Republic", "HU": "Hungary", "GR": "Greece",
    "JP": "Japan", "CN": "China", "HK": "Hong Kong", "TW": "Taiwan", "KR": "South Korea", "SG": "Singapore",
    "IN": "India", "AU": "Australia", "NZ": "New Zealand", "IL": "Israel", "BR": "Brazil", "MX": "Mexico",
    "ZA": "South Africa", "BM": "Bermuda", "KY": "Cayman Islands", "CL": "Chile", "CO": "Colombia", "CY": "Cyprus",
    "EG": "Egypt", "IS": "Iceland", "ID": "Indonesia", "IM": "Isle of Man", "JE": "Jersey", "GG": "Guernsey",
    "KW": "Kuwait", "MY": "Malaysia", "PH": "Philippines", "QA": "Qatar", "RO": "Romania", "SA": "Saudi Arabia",
    "TH": "Thailand", "TR": "Turkey", "AE": "United Arab Emirates", "UY": "Uruguay", "PE": "Peru", "AR": "Argentina",
    "VN": "Vietnam", "SK": "Slovakia", "SI": "Slovenia", "HR": "Croatia", "BG": "Bulgaria", "EE": "Estonia",
    "LV": "Latvia", "LT": "Lithuania", "MT": "Malta", "MC": "Monaco", "PR": "Puerto Rico", "PA": "Panama",
}  # fmt: skip
COUNTRY_CODES = {name: code for code, name in ISO_COUNTRIES.items()}


@dataclass(frozen=True)
class FundLookThrough:
    countries: dict[str, Decimal] | None  # fractions; "Other" kept as the source's unspecified remainder
    holdings: dict[str, Decimal] | None  # ISIN (or symbol) -> fraction, largest MAX_HOLDINGS
    names: dict[str, str] | None = None  # display names of the largest holdings, same keys


def normalize_country(name: str) -> str:
    name = name.strip()
    if name in COUNTRY_NAMES:
        return COUNTRY_NAMES[name]
    return re.sub(r"\s*\(the\)$", "", name)


def _fraction(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value)) / _PERCENT
    except (InvalidOperation, TypeError):
        return None
    return number if number.is_finite() and 0 < number <= 1 else None


def parse_countries(payload: Any) -> dict[str, Decimal] | None:
    if not isinstance(payload, list):
        return None
    countries: dict[str, Decimal] = {}
    for row in payload:
        if not isinstance(row, dict) or not isinstance(row.get("country"), str):
            continue
        if (weight := _fraction(row.get("exposure"))) is None:
            continue
        name = normalize_country(row["country"])
        countries[name] = countries.get(name, Decimal(0)) + weight
    total = sum(countries.values(), Decimal(0))
    # A breakdown that doesn't roughly add up to the whole fund is not trustworthy enough to replace estimates.
    if not countries or not Decimal("0.9") <= total <= Decimal("1.1"):
        return None
    return {name: weight / total for name, weight in countries.items()}


NAMED_HOLDINGS = 25


def _holding_key(row: dict[str, Any]) -> str | None:
    isin, symbol = row.get("isin"), row.get("symbol")
    key = isin if isinstance(isin, str) and _ISIN.fullmatch(isin) else symbol
    return key if isinstance(key, str) and key else None


def parse_holding_names(payload: Any, holdings: dict[str, Decimal] | None) -> dict[str, str] | None:
    """Names for the largest holdings only: enough to list them, without storing thousands of strings."""
    if not isinstance(payload, list) or not holdings:
        return None
    wanted = set(list(holdings)[:NAMED_HOLDINGS])
    names: dict[str, str] = {}
    for row in payload:
        if isinstance(row, dict) and (key := _holding_key(row)) in wanted and isinstance(row.get("name"), str):
            names[key] = row["name"].strip()[:120]
    return names or None


def parse_holdings(payload: Any) -> dict[str, Decimal] | None:
    if not isinstance(payload, list):
        return None
    holdings: dict[str, Decimal] = {}
    for row in payload:
        if not isinstance(row, dict) or (weight := _fraction(row.get("percent"))) is None:
            continue
        if key := _holding_key(row):
            holdings[key] = holdings.get(key, Decimal(0)) + weight
    if not holdings:
        return None
    return dict(sorted(holdings.items(), key=lambda item: item[1], reverse=True)[:MAX_HOLDINGS])


def _client(token: str, transport: httpx.BaseTransport | None) -> httpx.Client:
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "Jacklyn/1.0 (self-hosted portfolio tracker)"}
    return httpx.Client(timeout=15, headers=headers, transport=transport)


def _get(client: httpx.Client, path: str) -> Any:
    response = client.get(f"{BASE_URL}/{path}")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def fetch_fund(isin: str, token: str, *, transport: httpx.BaseTransport | None = None) -> FundLookThrough:
    """Country mix and holdings for one fund; parts the provider doesn't have come back as None."""
    if not _ISIN.fullmatch(isin):
        return FundLookThrough(None, None)
    with _client(token, transport) as client:
        countries = parse_countries(_get(client, f"etf/countries/{isin}"))
        payload = _get(client, f"etf/holdings/{isin}")
    holdings = parse_holdings(payload)
    return FundLookThrough(countries, holdings, parse_holding_names(payload, holdings))


def fetch_company_country(isin: str, token: str, *, transport: httpx.BaseTransport | None = None) -> str | None:
    """Headquarters country of a company, for stocks Yahoo has no country for."""
    if not _ISIN.fullmatch(isin):
        return None
    with _client(token, transport) as client:
        profile = _get(client, f"equity/profile/{isin}")
    code = profile.get("country") if isinstance(profile, dict) else None
    return ISO_COUNTRIES.get(code) if isinstance(code, str) else None

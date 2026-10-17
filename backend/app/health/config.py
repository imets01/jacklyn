"""Loads the reviewable data files: rules.toml (rules, thresholds, sources) and benchmarks.toml."""

import re
import tomllib
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast

DATA_DIR = Path(__file__).parent / "data"
Severity = Literal["good", "info", "warning", "problem"]
ValueFormat = Literal["percent", "points", "count", "multiple"]
SEVERITIES: tuple[Severity, ...] = ("problem", "warning", "info", "good")
OPERATORS = {">", ">=", "<", "<="}


@dataclass(frozen=True)
class Citation:
    id: str
    title: str
    publisher: str
    year: int
    url: str
    note: str | None = None


@dataclass(frozen=True)
class Level:
    severity: Severity
    op: str
    threshold: Decimal

    def matches(self, value: Decimal) -> bool:
        match self.op:
            case ">":
                return value > self.threshold
            case ">=":
                return value >= self.threshold
            case "<":
                return value < self.threshold
            case _:
                return value <= self.threshold


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    metric: str
    format: ValueFormat
    levels: tuple[Level, ...]
    message: str
    explanation: str
    threshold_note: str
    citations: tuple[Citation, ...]
    pass_message: str | None = None
    good_message: str | None = None


@dataclass(frozen=True)
class ProfileConfig:
    glide_start_equity: Decimal
    glide_years: int
    glide_target_equity: Decimal
    glide_floor_equity: Decimal
    glide_floor_years: int
    risk_adjustments: dict[str, Decimal]
    citation: Citation


@dataclass(frozen=True)
class RuleSet:
    rules: tuple[Rule, ...]
    score_start: int
    penalties: dict[str, int]
    absolute_band: Decimal
    relative_band: Decimal
    profile: ProfileConfig
    sources: dict[str, Citation]


@dataclass(frozen=True)
class SourceInfo:
    as_of: str
    title: str
    publisher: str
    url: str


@dataclass(frozen=True)
class IndexMapping:
    pattern: re.Pattern[str]
    not_pattern: re.Pattern[str] | None
    label: str
    broad: bool
    countries: dict[str, Decimal] | None  # None: spread like the benchmark

    def matches(self, name: str) -> bool:
        return bool(self.pattern.search(name)) and not (self.not_pattern and self.not_pattern.search(name))


@dataclass(frozen=True)
class Benchmark:
    name: str
    sectors: dict[str, Decimal]
    sectors_source: SourceInfo
    countries: dict[str, Decimal]
    countries_source: SourceInfo
    sector_names: dict[str, str]
    region_currencies: dict[str, str]
    indexes: tuple[IndexMapping, ...]

    def index_for(self, name: str | None) -> IndexMapping | None:
        if not name:
            return None
        return next((mapping for mapping in self.indexes if mapping.matches(name)), None)


def _decimals(raw: dict[str, Any]) -> dict[str, Decimal]:
    return {str(key): Decimal(str(value)) for key, value in raw.items()}


def _citation(key: str, raw: dict[str, Any]) -> Citation:
    return Citation(
        id=key,
        title=str(raw["title"]),
        publisher=str(raw["publisher"]),
        year=int(raw["year"]),
        url=str(raw["url"]),
        note=raw.get("note"),
    )


def parse_rules(data: dict[str, Any]) -> RuleSet:
    sources = {key: _citation(key, raw) for key, raw in data["sources"].items()}
    rules = []
    for raw in data["rule"]:
        levels = []
        for level in raw["levels"]:
            if level["severity"] not in SEVERITIES or level["op"] not in OPERATORS:
                raise ValueError(f"Rule {raw['id']}: bad level {level}")
            levels.append(Level(cast(Severity, level["severity"]), level["op"], Decimal(str(level["threshold"]))))
        missing = [key for key in raw["citations"] if key not in sources]
        if missing or not raw["citations"]:
            raise ValueError(f"Rule {raw['id']} needs citations from [sources] (missing: {missing})")
        rules.append(
            Rule(
                id=raw["id"],
                title=raw["title"],
                metric=raw["metric"],
                format=raw["format"],
                levels=tuple(sorted(levels, key=lambda lv: SEVERITIES.index(lv.severity))),
                message=raw.get("message", ""),
                explanation=raw["explanation"],
                threshold_note=raw["threshold_note"],
                citations=tuple(sources[key] for key in raw["citations"]),
                pass_message=raw.get("pass_message"),
                good_message=raw.get("good_message"),
            )
        )
    profile = data["profile"]
    return RuleSet(
        rules=tuple(rules),
        score_start=int(data["score"]["start"]),
        penalties={str(key): int(value) for key, value in data["score"]["penalties"].items()},
        absolute_band=Decimal(data["rebalancing"]["absolute_band"]),
        relative_band=Decimal(data["rebalancing"]["relative_band"]),
        profile=ProfileConfig(
            glide_start_equity=Decimal(profile["glide_start_equity"]),
            glide_years=int(profile["glide_years"]),
            glide_target_equity=Decimal(profile["glide_target_equity"]),
            glide_floor_equity=Decimal(profile["glide_floor_equity"]),
            glide_floor_years=int(profile["glide_floor_years"]),
            risk_adjustments=_decimals(profile["risk_adjustments"]),
            citation=sources[profile["glide_citation"]],
        ),
        sources=sources,
    )


def _source(raw: dict[str, Any]) -> SourceInfo:
    return SourceInfo(
        as_of=str(raw["as_of"]), title=raw["source_title"], publisher=raw["source_publisher"], url=raw["source_url"]
    )


def parse_benchmark(data: dict[str, Any]) -> Benchmark:
    bench = data["benchmark"]
    indexes = []
    for raw in data["index"]:
        countries = raw["countries"]
        indexes.append(
            IndexMapping(
                pattern=re.compile(raw["pattern"], re.IGNORECASE),
                not_pattern=re.compile(raw["not_pattern"], re.IGNORECASE) if raw.get("not_pattern") else None,
                label=raw["label"],
                broad=bool(raw.get("broad", False)),
                countries=None if countries == "benchmark" else _decimals(countries),
            )
        )
    return Benchmark(
        name=bench["name"],
        sectors=_decimals(bench["sectors"]["weights"]),
        sectors_source=_source(bench["sectors"]),
        countries=_decimals(bench["countries"]["weights"]),
        countries_source=_source(bench["countries"]),
        sector_names={str(key): str(value) for key, value in data["sector_names"].items()},
        region_currencies={str(key): str(value) for key, value in data["region_currencies"].items()},
        indexes=tuple(indexes),
    )


@lru_cache(maxsize=1)
def load_rules() -> RuleSet:
    with (DATA_DIR / "rules.toml").open("rb") as handle:
        return parse_rules(tomllib.load(handle))


@lru_cache(maxsize=1)
def load_benchmark() -> Benchmark:
    with (DATA_DIR / "benchmarks.toml").open("rb") as handle:
        return parse_benchmark(tomllib.load(handle))

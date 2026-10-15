"""Parser discovery. Add a new broker by appending its class to ``BROKER_PARSERS``."""

from dataclasses import dataclass

from app.parsers.base import BaseBrokerParser, FileSample
from app.parsers.erste import ErsteNetBrokerParser
from app.parsers.generic_csv import ColumnMapping, GenericCSVParser
from app.parsers.ibkr import IbkrActivityParser
from app.parsers.lightyear import LightyearParser

BROKER_PARSERS: tuple[type[BaseBrokerParser], ...] = (
    IbkrActivityParser,
    LightyearParser,
    ErsteNetBrokerParser,
)
ALL_PARSERS: tuple[type[BaseBrokerParser], ...] = (*BROKER_PARSERS, GenericCSVParser)

DETECTION_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class Detection:
    parser: type[BaseBrokerParser]
    confidence: float


def detect_parser(sample: FileSample) -> Detection | None:
    scored = [Detection(p, p.detect(sample)) for p in BROKER_PARSERS]
    best = max(scored, key=lambda d: d.confidence, default=None)
    if best is None or best.confidence < DETECTION_THRESHOLD:
        return None
    return best


def get_parser_class(key: str) -> type[BaseBrokerParser]:
    for parser in ALL_PARSERS:
        if parser.key == key:
            return parser
    raise KeyError(key)


def instantiate(key: str, mapping: ColumnMapping | None = None) -> BaseBrokerParser:
    if key == GenericCSVParser.key:
        if mapping is None:
            raise ValueError("The generic parser needs a column mapping")
        return GenericCSVParser(mapping)
    cls = get_parser_class(key)
    return cls()

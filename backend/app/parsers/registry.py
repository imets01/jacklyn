from dataclasses import dataclass

from app.parsers.base import BaseBrokerParser
from app.parsers.erste import ErsteNetBrokerParser
from app.parsers.erste_reports import ErsteDailyReportParser
from app.parsers.ibkr import IBKRActivityCSVParser, IBKRFlexXMLParser
from app.parsers.lightyear import LightyearCSVParser
from app.parsers.revolut import RevolutTradingParser
from app.parsers.source import SourceFile

# Tier-1 presets, tried in this order; the highest confidence wins.
PRESET_PARSERS: tuple[BaseBrokerParser, ...] = (
    IBKRFlexXMLParser(),
    IBKRActivityCSVParser(),
    LightyearCSVParser(),
    RevolutTradingParser(),
    ErsteDailyReportParser(),
    ErsteNetBrokerParser(),
)
DETECTION_THRESHOLD = 0.5


@dataclass(frozen=True)
class Detection:
    parser: BaseBrokerParser
    confidence: float


def detect_parser(source: SourceFile) -> Detection | None:
    best: Detection | None = None
    for parser in PRESET_PARSERS:
        confidence = parser.detect(source)
        if confidence >= DETECTION_THRESHOLD and (best is None or confidence > best.confidence):
            best = Detection(parser, confidence)
    return best


def get_parser(key: str) -> BaseBrokerParser | None:
    return next((parser for parser in PRESET_PARSERS if parser.key == key), None)

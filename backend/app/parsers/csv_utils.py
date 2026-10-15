"""Decoding, dialect sniffing and header helpers shared by all CSV parsers."""

import csv
import hashlib
import io
import re
import unicodedata
from datetime import date, datetime

from app.parsers.base import FileSample

_CANDIDATE_DELIMITERS = ",;\t|"
_SAMPLE_ROWS = 25


class UndecodableFileError(ValueError):
    pass


def decode_bytes(data: bytes) -> str:
    """Decode an upload. Brokers ship UTF-8, UTF-16 (Excel) and CP1250 (Hungarian banks)."""
    if data.startswith((b"PK\x03\x04", b"\xd0\xcf\x11\xe0")):
        raise UndecodableFileError("Excel workbooks are not supported yet; export as CSV")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    for encoding in ("utf-8-sig", "cp1250"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "\x00" in text:
            break
        return text
    raise UndecodableFileError("Could not decode file; expected UTF-8, UTF-16 or Windows-1250")


def sniff_delimiter(text: str) -> str:
    head = "\n".join(text.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(head, delimiters=_CANDIDATE_DELIMITERS).delimiter
    except csv.Error:
        counts = {d: head.count(d) for d in _CANDIDATE_DELIMITERS}
        return max(counts, key=lambda d: counts[d]) if any(counts.values()) else ","


def read_rows(text: str, delimiter: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [row for row in reader if any(cell.strip() for cell in row)]


def build_sample(filename: str, text: str) -> FileSample:
    delimiter = sniff_delimiter(text)
    rows = read_rows("\n".join(text.splitlines()[: _SAMPLE_ROWS + 1]), delimiter)
    headers = [h.strip() for h in rows[0]] if rows else []
    return FileSample(
        filename=filename,
        text=text,
        delimiter=delimiter,
        headers=headers,
        rows=rows[1:],
    )


def normalise_header(header: str) -> str:
    """``"Price / Share (€)"`` -> ``"price share"``; strips accents so Hungarian headers match."""
    ascii_text = (
        unicodedata.normalize("NFKD", header).encode("ascii", "ignore").decode("ascii").lower()
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def header_signature(headers: list[str]) -> str:
    """Stable hash of a header row, used to auto-match saved mappings."""
    canonical = "|".join(normalise_header(h) for h in headers)
    return hashlib.sha256(canonical.encode()).hexdigest()


# Ordered by how common they are in broker exports; first match wins.
COMMON_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d, %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d.%m.%Y",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%Y.%m.%d.",
    "%Y.%m.%d",
    "%Y.%m.%d. %H:%M:%S",
    "%Y.%m.%d %H:%M:%S",
    "%m/%d/%Y",
    "%Y%m%d",
)


def parse_date(value: str, fmt: str | None = None) -> date:
    raw = value.strip()
    if fmt:
        return datetime.strptime(raw, fmt).date()
    for candidate in COMMON_DATE_FORMATS:
        try:
            return datetime.strptime(raw, candidate).date()
        except ValueError:
            continue
    # ISO timestamps with offsets / fractional seconds.
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError as exc:
        raise ValueError(f"Unrecognised date: {value!r}") from exc


def guess_date_format(values: list[str]) -> str | None:
    """Pick the first format that parses every non-empty sample value."""
    cleaned = [v.strip() for v in values if v.strip()]
    if not cleaned:
        return None
    for fmt in COMMON_DATE_FORMATS:
        try:
            for v in cleaned:
                datetime.strptime(v, fmt)
        except ValueError:
            continue
        return fmt
    return None


def guess_decimal_separator(values: list[str]) -> str:
    """``1.234,56`` / ``12,5`` -> ``","``; anything else -> ``"."``."""
    comma_votes = dot_votes = 0
    for v in values:
        s = re.sub(r"[^0-9.,]", "", v)
        if not s:
            continue
        last_comma, last_dot = s.rfind(","), s.rfind(".")
        if last_comma > last_dot and len(s) - last_comma - 1 != 3:
            comma_votes += 1
        elif last_dot > last_comma:
            dot_votes += 1
        elif last_comma > last_dot and last_dot != -1:
            comma_votes += 1
    return "," if comma_votes > dot_votes else "."

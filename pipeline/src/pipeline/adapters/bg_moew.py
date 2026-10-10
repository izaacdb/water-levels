"""Bulgaria: MOEW daily bulletin on the state of waters.

(Ежедневен бюлетин за състоянието на водите)

Each day the ministry publishes a bulletin covering the 52 "complex and
significant" reservoirs. Recent editions are Word documents (converted here
with headless LibreOffice); older ones were PDFs. The ministry's site no
longer serves old attachments, so history comes from Internet Archive
captures of the official files, one per ISO week.
"""

from __future__ import annotations

import base64
import html
import io
import json
import logging
import re
import subprocess
import tempfile
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import httpx
import pdfplumber
import polars as pl

from pipeline.adapters.base import OBSERVATION_SCHEMA, SourceMeta

log = logging.getLogger(__name__)

SITE = "https://www.moew.government.bg"
LISTING = f"{SITE}/bg/prescentur/byuletini-na-mosv/vodi/"
ARCHIVE_FOLDERS = [
    "moew.government.bg/static/media/ups/tiny/Daily%20Bulletin/",
    "moew.government.bg/static/media/ups/tiny/Water%20Daily%20Bulletin/",
]
CDX = "https://web.archive.org/cdx/search/cdx"

# Bulgarian official transliteration (Streamlined System), for stable ASCII keys.
_TRANSLIT = dict(
    zip(
        "абвгдежзийклмнопрстуфхцчшщъьюя",
        [
            "a",
            "b",
            "v",
            "g",
            "d",
            "e",
            "zh",
            "z",
            "i",
            "y",
            "k",
            "l",
            "m",
            "n",
            "o",
            "p",
            "r",
            "s",
            "t",
            "u",
            "f",
            "h",
            "ts",
            "ch",
            "sh",
            "sht",
            "a",
            "y",
            "yu",
            "ya",
        ],
        strict=True,
    )
)
_MONTHS = {
    "yanuari": 1, "fevruari": 2, "mart": 3, "april": 4, "maj": 5, "may": 5, "yuni": 6,
    "yuli": 7, "avgust": 8, "septemvri": 9, "oktomvri": 10, "noemvri": 11, "dekemvri": 12,
}  # fmt: skip
_DATE = re.compile(r"от\s+(\d{2})\.(\d{2})\.(\d{4})")
_FILE_DATE = re.compile(r"(\d{2})(\d{2})(\d{4})_Bulletin_Daily\.(pdf|doc)", re.IGNORECASE)
_NUMBER = re.compile(r"^-?\d+[.,]\d+$")


def bg_key(name: str) -> str:
    latin = "".join(_TRANSLIT.get(ch, ch) for ch in name.lower())
    return re.sub(r"[^a-z0-9]+", "-", latin).strip("-")


def clean_name(raw: str) -> str:
    """'Огняново  - за рез.водоснабдяване **' -> 'Огняново'."""
    name = " ".join(raw.replace("*", "").split())
    return name.split(" - ")[0].strip()


def bulletin_date_from_slug(slug: str) -> date:
    m = re.search(r"-za-(\d{1,2})-([a-z]+)-(\d{4})", slug)
    if not m:
        raise ValueError(f"no date in bulletin slug {slug!r}")
    return date(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)))


def _float(text: str) -> float:
    return float(text.replace(",", "."))


def _rows_to_frame(rows: list[list[str]], text: str, fallback: date | None = None) -> pl.DataFrame:
    m = _DATE.search(text)
    if m:
        observed = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    elif fallback:
        observed = fallback  # some 2020 layouts keep the date out of the text layer
    else:
        raise ValueError("no date found in bulletin")
    out, seen = [], set()
    for cells in rows:
        # A reservoir row: number, basin directorate, name, total, dead, available volume, ...
        # Unnumbered rows are cascade subtotals and would double count.
        if len(cells) < 6 or not cells[0].isdigit() or not cells[1].startswith("БД"):
            continue
        name = clean_name(cells[2])
        total, available = cells[3], cells[5]
        if not (_NUMBER.match(total) and _NUMBER.match(available)):
            continue  # "не се получава ежедневна информация": no reading today
        key = bg_key(name)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "source_key": key,
                "name": name,
                "group": cells[1],
                "observed_on": observed,
                "volume_hm3": _float(available),
                "capacity_hm3": _float(total),
            }
        )
    if not out:
        raise ValueError("no reservoir rows in bulletin")
    return resolve_clipped_names(pl.DataFrame(out, schema=OBSERVATION_SCHEMA))


def _cell_text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def parse_html(raw: bytes, fallback: date | None = None) -> pl.DataFrame:
    """A bulletin converted to HTML by LibreOffice."""
    doc = raw.decode("utf-8", errors="replace")
    rows = [
        [c for c in (_cell_text(td) for td in re.findall(r"<td.*?</td>", tr, re.S)) if c]
        for tr in re.findall(r"<tr.*?</tr>", doc, re.S)
    ]
    return _rows_to_frame(rows, _cell_text(doc), fallback)


def parse_pdf(raw: bytes, fallback: date | None = None) -> pl.DataFrame:
    rows: list[list[str]] = []
    text = ""
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            text += (page.extract_text() or "") + "\n"
            for table in page.extract_tables():
                rows += [[" ".join(c.split()) for c in r if c and c.strip()] for r in table]
    return _rows_to_frame(rows, text, fallback)


def resolve_clipped_names(obs: pl.DataFrame) -> pl.DataFrame:
    """Archived PDFs clip long names at the cell edge ('Ивайловград' -> 'ivaylovgra').
    An unknown key is matched as a prefix of a registry key; when several fit, the
    closest capacity wins (each row carries the reservoir's total volume)."""
    from pipeline.registry import load_registry  # local: registry imports nothing from here

    registry = load_registry("BG").select(
        "source_key", pl.col("capacity_hm3").cast(pl.Float64, strict=False)
    )
    known: dict[str, float | None] = dict(registry.iter_rows())

    def resolve(key: str, capacity: float) -> str:
        if key in known:
            return key
        candidates = [k for k in known if k.startswith(key)]
        if not candidates:
            return key
        return min(candidates, key=lambda k: abs((known[k] or 0) - capacity))

    keys = [resolve(k, c) for k, c in obs.select("source_key", "capacity_hm3").iter_rows()]
    return obs.with_columns(pl.Series("source_key", keys, dtype=pl.String))


def _complete(raw: bytes) -> bool:
    """Archived PDFs are sometimes truncated; a complete one ends with an EOF marker."""
    return not raw.startswith(b"%PDF") or b"%%EOF" in raw[-2048:]


def _envelope(day: date, content: bytes) -> bytes:
    return json.dumps(
        {"date": day.isoformat(), "content": base64.b64encode(content).decode()}
    ).encode()


def word_to_html(raw: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "bulletin.doc"
        src.write_bytes(raw)
        subprocess.run(
            [
                "soffice",
                "--headless",
                "--convert-to",
                "html:HTML (StarWriter)",
                "--outdir",
                tmp,
                str(src),
            ],
            check=True,
            capture_output=True,
            timeout=180,
        )
        return (Path(tmp) / "bulletin.html").read_bytes()


class MoewAdapter:
    meta = SourceMeta(
        id="bg-moew",
        country="BG",
        name="МОСВ — Ежедневен бюлетин за състоянието на водите",
        url=LISTING,
    )

    def fetch(self, client: httpx.Client) -> bytes:
        listing = client.get(LISTING, timeout=60, follow_redirects=True)
        listing.raise_for_status()
        slug = re.search(
            r'href="(/bg/ejedneven-byuletin-za-sustoyanieto-na-vodite[^"#]*)"', listing.text
        )
        if not slug:
            raise ValueError("no bulletin link on the MOEW listing page")
        page = client.get(SITE + slug.group(1), timeout=60, follow_redirects=True)
        page.raise_for_status()
        attachment = re.search(
            r'href="(/static/media/ups/tiny/[^"]*_Bulletin_Daily\.(?:doc|pdf))"', page.text
        )
        if not attachment:
            raise ValueError(f"no bulletin attachment on {slug.group(1)}")
        response = client.get(SITE + attachment.group(1), timeout=120)
        response.raise_for_status()
        return response.content

    def fetch_history(self, client: httpx.Client) -> Iterator[bytes]:
        """One archived bulletin per ISO week (the latest that week), oldest first."""
        by_week: dict[tuple[int, int], list[tuple[date, str]]] = {}
        for folder in ARCHIVE_FOLDERS:
            try:
                index = client.get(
                    CDX,
                    params={
                        "url": folder,
                        "matchType": "prefix",
                        "output": "json",
                        "filter": "statuscode:200",
                        "collapse": "urlkey",
                        "fl": "timestamp,original",
                    },
                    timeout=180,
                )
                index.raise_for_status()
                captures = index.json()[1:]
            except (httpx.HTTPError, ValueError) as err:
                log.warning("archive index unavailable for %s: %s", folder, err)
                continue
            for ts, original in captures:
                m = _FILE_DATE.search(original)
                if not m:
                    continue
                day = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                url = f"https://web.archive.org/web/{ts}id_/{original}"
                by_week.setdefault(day.isocalendar()[:2], []).append((day, url))
        for week in sorted(by_week):
            # Latest edition first; some captures are truncated, so fall back within the week.
            for day, url in sorted(by_week[week], reverse=True):
                time.sleep(1)  # be gentle with the Internet Archive
                try:
                    response = client.get(url, timeout=120, follow_redirects=True)
                    response.raise_for_status()
                except httpx.HTTPError as err:
                    log.warning("skipping archived bulletin %s: %s", url, err)
                    continue
                if not _complete(response.content):
                    log.warning("skipping truncated archived bulletin %s", url)
                    continue
                yield _envelope(day, response.content)
                break

    def parse(self, raw: bytes) -> pl.DataFrame:
        fallback = None
        if raw.startswith(b'{"date"'):  # archived edition with the date from its file name
            envelope = json.loads(raw)
            fallback, raw = (
                date.fromisoformat(envelope["date"]),
                base64.b64decode(envelope["content"]),
            )
        if raw.startswith(b"%PDF"):
            return parse_pdf(raw, fallback)
        if raw.startswith(b"\xd0\xcf\x11\xe0"):  # OLE2: a Word 97-2003 document
            try:
                return parse_html(word_to_html(raw), fallback)
            except (subprocess.CalledProcessError, FileNotFoundError) as err:
                raise ValueError(f"could not convert Word bulletin: {err}") from err
        return parse_html(raw, fallback)

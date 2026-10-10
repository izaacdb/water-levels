"""Spain: MITECO weekly hydrological bulletin reservoir database.

MITECO publishes the full per-reservoir history (1988 onwards, every Tuesday)
as a single MS Access database inside a ZIP, refreshed weekly. We read it with
mdbtools (``mdb-export``), so the history and the latest week come from the
same download.
"""

from __future__ import annotations

import io
import subprocess
import tempfile
import zipfile
from pathlib import Path

import httpx
import polars as pl

from pipeline.adapters.base import OBSERVATION_SCHEMA, SourceMeta, slugify

DATA_URL = (
    "https://www.miteco.gob.es/content/dam/miteco/es/agua/temas/"
    "evaluacion-de-los-recursos-hidricos/boletin-hidrologico/Historico-de-embalses/"
    "BD-Embalses.zip"
)
TABLE_PREFIX = "T_Datos Embalses"


class MitecoAdapter:
    meta = SourceMeta(
        id="es-miteco",
        country="ES",
        name="MITECO — Boletín Hidrológico semanal",
        url="https://www.miteco.gob.es/es/agua/temas/evaluacion-de-los-recursos-hidricos/boletin-hidrologico.html",
    )

    def fetch(self, client: httpx.Client) -> bytes:
        response = client.get(DATA_URL, follow_redirects=True, timeout=120)
        response.raise_for_status()
        return response.content

    def parse(self, raw: bytes) -> pl.DataFrame:
        return parse_csv(_export_csv(raw))


def _export_csv(raw_zip: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        mdb_names = [n for n in zf.namelist() if n.lower().endswith(".mdb")]
        if not mdb_names:
            raise ValueError(f"no .mdb database in MITECO archive: {zf.namelist()}")
        with tempfile.TemporaryDirectory() as tmp:
            mdb_path = Path(zf.extract(mdb_names[0], tmp))
            tables = _run("mdb-tables", "-1", str(mdb_path)).splitlines()
            table = next((t for t in tables if t.startswith(TABLE_PREFIX)), None)
            if table is None:
                raise ValueError(f"no '{TABLE_PREFIX}*' table in MITECO database: {tables}")
            return _run("mdb-export", "-T", "%Y-%m-%d", str(mdb_path), table)


def _run(*cmd: str) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def _decimal(col: str) -> pl.Expr:
    return pl.col(col).str.replace(",", ".", literal=True).cast(pl.Float64, strict=False)


def parse_csv(text: str) -> pl.DataFrame:
    """Parse ``mdb-export`` output (decimal commas, ISO dates) into observations."""
    df = pl.read_csv(io.StringIO(text), infer_schema=False)
    slugs = {name: slugify(name) for name in df["EMBALSE_NOMBRE"].unique().to_list()}
    return (
        df.select(
            pl.col("EMBALSE_NOMBRE").replace_strict(slugs).alias("source_key"),
            pl.col("EMBALSE_NOMBRE").alias("name"),
            pl.col("AMBITO_NOMBRE").alias("group"),
            pl.col("FECHA").str.to_date("%Y-%m-%d").alias("observed_on"),
            _decimal("AGUA_ACTUAL").alias("volume_hm3"),
            _decimal("AGUA_TOTAL").alias("capacity_hm3"),
        )
        # Rows without a usable capacity can't be expressed as % full.
        .filter(pl.col("volume_hm3").is_not_null() & (pl.col("capacity_hm3") > 0))
        .cast(OBSERVATION_SCHEMA)  # type: ignore[arg-type]
    )

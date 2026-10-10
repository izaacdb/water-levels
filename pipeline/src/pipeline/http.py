"""HTTP client shared by every adapter."""

from __future__ import annotations

import ssl
from pathlib import Path

import certifi
import httpx

USER_AGENT = "water-levels/0.1 (+https://github.com/izaacdb/water-levels)"
CERTS_DIR = Path(__file__).resolve().parents[2] / "certs"


def ssl_context() -> ssl.SSLContext:
    """certifi's roots plus intermediates that some sources fail to send (see certs/README.md)."""
    ctx = ssl.create_default_context(cafile=certifi.where())
    for pem in sorted(CERTS_DIR.glob("*.pem")):
        ctx.load_verify_locations(cafile=str(pem))
    return ctx


def client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, verify=ssl_context())

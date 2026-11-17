"""
Pure catalogue rules shared by the admin schemas and services (Phase 9 M3):
slug / SKU / image-URL formats and the stock-status rule. No database, no HTTP.
"""

import re
import unicodedata
from typing import Optional

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKU_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")
IMAGE_URL_PATTERN = re.compile(r"^(https?://[^\s]+|/[^\s]*)$")


def slugify(text: str) -> str:
    """'Rolled Oats & Honey!' -> 'rolled-oats-honey'. Accents are folded to ASCII;
    anything else becomes a hyphen. May return '' (e.g. for '!!!')."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")


def clean_text(value: Optional[str]) -> Optional[str]:
    """Strip; blank becomes None."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def normalise_slug(value: str) -> str:
    slug = value.strip().lower()
    if not SLUG_PATTERN.match(slug):
        raise ValueError("Use lowercase letters, digits and single hyphens only (e.g. 'rolled-oats').")
    return slug


def normalise_sku(value: str) -> str:
    sku = value.strip().upper()
    if not SKU_PATTERN.match(sku):
        raise ValueError("Use letters, digits, '.', '_' and '-' only, starting with a letter or digit.")
    return sku


def validate_image_url(value: str) -> str:
    url = value.strip()
    if url.startswith("//"):
        raise ValueError("Protocol-relative URLs are not allowed.")
    if not IMAGE_URL_PATTERN.match(url):
        raise ValueError("Must be an http(s) URL or a site path starting with '/'.")
    return url


def stock_status(quantity: Optional[int], reserved: Optional[int], threshold: Optional[int]) -> str:
    """'out' | 'low' | 'ok' by the shop's own rule: available = quantity - reserved;
    out = available <= 0; low = 0 < available <= threshold (NULL = 0); else ok.
    No inventory row at all is 'out'."""
    if quantity is None:
        return "out"
    available = quantity - (reserved or 0)
    if available <= 0:
        return "out"
    if available <= (threshold or 0):
        return "low"
    return "ok"

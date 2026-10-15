"""
Shop logos and storefront photos.

Lookup order (no network, no scraping — files are added by hand):
  1. assets/shops/<shop_id>.(jpg|jpeg|png|webp)  storefront photo from the seed walk
  2. assets/logos/<chain>.(png|svg|jpg|webp)     chain logo
  3. Brand-coloured initials badge (inline SVG)  always available
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

from models import Shop

ASSETS_DIR = Path(__file__).parent / "assets"
LOGO_DIR = ASSETS_DIR / "logos"
SHOP_PHOTO_DIR = ASSETS_DIR / "shops"

_IMAGE_EXTS = (".png", ".svg", ".jpg", ".jpeg", ".webp")
_MIME = {".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg",
         ".jpeg": "image/jpeg", ".webp": "image/webp"}

# chain → (badge text, background, text colour)
_BADGES = {
    "tesco":             ("T",   "#00539F", "#FFFFFF"),
    "sainsburys":        ("S",   "#F06C00", "#FFFFFF"),
    "waitrose":          ("W",   "#5C8018", "#FFFFFF"),
    "marks-and-spencer": ("M&S", "#1E1E1E", "#FFFFFF"),
    "lidl":              ("L",   "#0050AA", "#FFF000"),
    "pret":              ("P",   "#862633", "#FFFFFF"),
}


def _find(directory: Path, stem: str) -> Path | None:
    for ext in _IMAGE_EXTS:
        path = directory / f"{stem}{ext}"
        if path.exists():
            return path
    return None


@lru_cache(maxsize=64)
def _data_uri(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:{_MIME[path.suffix.lower()]};base64,{data}"


def storefront_path(shop: Shop) -> Path | None:
    """Storefront photo for this branch: a hand-added asset, else one set from an upload."""
    from photo_store import storefront_upload
    return _find(SHOP_PHOTO_DIR, shop.shop_id) or storefront_upload(shop.shop_id)


def logo_html(shop: Shop, size: int = 28) -> str:
    """Inline <img> or SVG badge for the chain logo, safe to drop into st.markdown HTML."""
    logo = _find(LOGO_DIR, shop.chain)
    style = f"width:{size}px;height:{size}px;border-radius:6px;vertical-align:middle;margin-right:8px"
    if logo is not None:
        return f'<img src="{_data_uri(logo)}" alt="{shop.name}" style="{style};object-fit:contain;background:#fff">'

    text, bg, fg = _BADGES.get(shop.chain, (shop.name[:1].upper(), "#94A3B8", "#FFFFFF"))
    font = size * (0.32 if len(text) > 2 else 0.5)
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" style="{style}" '
        f'role="img" aria-label="{shop.name}">'
        f'<rect width="{size}" height="{size}" rx="6" fill="{bg}"/>'
        f'<text x="50%" y="50%" dominant-baseline="central" text-anchor="middle" '
        f'font-family="sans-serif" font-weight="700" font-size="{font:.0f}" fill="{fg}">{text.replace("&", "&amp;")}</text>'
        f'</svg>'
    )

"""
Shop logos and storefront photos.

Lookup order (no network, no scraping — files are added by hand):
  1. assets/shops/<shop_id>.(jpg|jpeg|png|webp)  storefront photo from the seed walk
  2. assets/logos/<chain>.(png|svg|jpg|webp)     chain logo
  3. Brand-coloured initials badge (.dl-shop)    always available
Colours come from design/tokens.json (shop-* / on-shop-* tokens) — never hex here.
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

# chain → (badge text, text-colour token). Background token is shop-<chain>;
# the matching .dl-shop--<chain> class in design/components.css pairs them.
_BADGES = {
    "tesco":             ("T",   "on-shop-light"),
    "sainsburys":        ("S",   "on-shop-dark"),
    "waitrose":          ("W",   "on-shop-light"),
    "marks-and-spencer": ("M&S", "on-shop-light"),
    "lidl":              ("L",   "on-shop-lidl"),
    "pret":              ("P",   "on-shop-light"),
}
_BADGE_BASE_PX = 28          # .dl-shop size; other sizes scale with CSS zoom


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


def logo_html(shop: Shop, size: int = 28, standalone: bool = False) -> str:
    """
    Chain logo <img>, or the initials badge, safe to drop into st.markdown HTML.
    standalone=True inlines resolved token values for places the page CSS can't
    reach (the Folium map popup is its own iframe).
    """
    from theme import token, type_css

    logo = _find(LOGO_DIR, shop.chain)
    surface = token("surface") if standalone else "var(--surface)"
    radius = token("radius-badge") if standalone else "var(--radius-badge)"
    gap = token("space-2") if standalone else "var(--space-2)"
    if logo is not None:
        return (f'<img src="{_data_uri(logo)}" alt="{shop.name}" style="width:{size}px;height:{size}px;'
                f'border-radius:{radius};vertical-align:middle;margin-right:{gap};'
                f'object-fit:contain;background:{surface}">')

    known = shop.chain in _BADGES
    text, fg = _BADGES.get(shop.chain, (shop.name[:1].upper(), "text"))
    label = text.replace("&", "&amp;")
    zoom = size / _BADGE_BASE_PX
    if standalone:
        bg = token(f"shop-{shop.chain}" if known else "shop-fallback")
        text_style = type_css("caption" if len(text) > 2 else "label")   # "M&S" needs the smaller size
        return (f'<span role="img" aria-label="{shop.name}" style="display:inline-flex;align-items:center;'
                f'justify-content:center;width:{_BADGE_BASE_PX}px;height:{_BADGE_BASE_PX}px;zoom:{zoom:.3f};'
                f'border-radius:{radius};vertical-align:middle;margin-right:{gap};background:{bg};'
                f'color:{token(fg)};{text_style};font-weight:700">{label}</span>')
    classes = f"dl-shop dl-shop--{shop.chain if known else 'fallback'}" + (" dl-shop--sm-text" if len(text) > 2 else "")
    return (f'<span class="{classes}" role="img" aria-label="{shop.name}" '
            f'style="zoom:{zoom:.3f};vertical-align:middle;margin-right:var(--space-2)">{label}</span>')

"""
Deeelicious design tokens → CSS, injected into Streamlit.

Single source of truth: design/tokens.json. Never hand-copy hex values into app code;
use the CSS variables (var(--primary)) or the .dl-* classes in design/components.css.

Usage in app.py (once per page, before other output):
    from theme import inject_theme
    inject_theme()

Regenerate the static stylesheet used by the component previews:
    python theme.py        # writes design/tokens.css
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DESIGN_DIR = Path(__file__).parent / "design"
TOKENS_PATH = DESIGN_DIR / "tokens.json"
COMPONENTS_CSS_PATH = DESIGN_DIR / "components.css"
TOKENS_CSS_PATH = DESIGN_DIR / "tokens.css"

_ALIAS = re.compile(r"^\{(.+)\}$")


def _value(raw) -> str:
    """A token value as CSS; colour aliases like "{text}" become var(--text)."""
    if isinstance(raw, dict):  # per-theme value: light only for launch
        raw = raw.get("light") or next(iter(raw.values()))
    match = _ALIAS.match(str(raw))
    return f"var(--{match.group(1)})" if match else str(raw)


@lru_cache(maxsize=1)
def tokens_css() -> str:
    """CSS custom properties for every token, plus a class per type style."""
    tokens = json.loads(TOKENS_PATH.read_text())
    lines = [":root {"]
    for tok in tokens["color"]["tokens"]:
        lines.append(f"  --{tok['name']}: {_value(tok['value'])};")
    for family in ("spacing", "radius", "shadow", "borderWidth"):
        for tok in tokens.get(family, {}).get("tokens", []):
            lines.append(f"  --{tok['name']}: {_value(tok['value'])};")
    for key, stack in tokens["type"]["families"].items():
        lines.append(f"  --font-{key}: {stack};")
    lines.append("}")
    for group in tokens["type"]["groups"]:
        for style in group["styles"]:
            family = style.get("family", group["family"])
            rules = [
                f"font-family: var(--font-{family})",
                f"font-size: {style['fontSize']}",
                f"line-height: {style['lineHeight']}",
                f"font-weight: {style['fontWeight']}",
            ]
            if "letterSpacing" in style:
                rules.append(f"letter-spacing: {style['letterSpacing']}")
            if style["name"] in ("price", "price-sm", "score-numeral"):
                rules.append("font-variant-numeric: tabular-nums")
            lines.append(f".dl-type-{style['name']} {{ {'; '.join(rules)}; }}")
    return "\n".join(lines) + "\n"


@lru_cache(maxsize=1)
def page_css() -> str:
    """Everything the app needs: fonts @import first, then tokens, then component classes."""
    components = COMPONENTS_CSS_PATH.read_text()
    imports = [l for l in components.splitlines() if l.startswith("@import")]
    rest = "\n".join(l for l in components.splitlines() if not l.startswith("@import"))
    return "\n".join(imports) + "\n" + tokens_css() + rest


def inject_theme() -> None:
    """Inject the design system CSS into the current Streamlit page."""
    import streamlit as st

    st.markdown(f"<style>\n{page_css()}\n</style>", unsafe_allow_html=True)


if __name__ == "__main__":
    TOKENS_CSS_PATH.write_text("/* Deeelicious — generated from tokens.json by theme.py */\n" + tokens_css())
    print(f"wrote {TOKENS_CSS_PATH}")

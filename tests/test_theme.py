"""Design system: tokens resolve, and app code never hard-codes colours or font sizes."""

import re
from pathlib import Path

import theme

ROOT = Path(__file__).parent.parent
UI_FILES = ["app.py", "demo.py", "map_view.py", "shop_images.py"]


def test_token_resolves_aliases():
    assert theme.token("primary") == "#0f7b5f"
    assert theme.token("rank-ink") == theme.token("text")          # "{text}" alias
    assert theme.token("radius-badge") == "6px"


def test_type_css_is_attribute_safe():
    css = theme.type_css("caption")
    assert "font-size:11px" in css and '"' not in css


def test_page_css_defines_every_class_the_app_uses():
    css = theme.page_css()
    used = set()
    for name in UI_FILES:
        used |= set(re.findall(r"\b(dl-[a-z0-9_-]+)", (ROOT / name).read_text()))
    used = {c for c in used if not c.endswith("-")}           # f-string stems, checked below
    defined = set(re.findall(r"\.(dl-[a-z0-9_-]+)", css))
    assert used - defined == set()
    # dynamic modifiers built in code
    for band in ("high", "mid", "low"):
        assert f"dl-score--{band}" in defined
    for chain in ("tesco", "sainsburys", "waitrose", "marks-and-spencer", "lidl", "pret", "fallback"):
        assert f"dl-shop--{chain}" in defined


def test_no_hard_coded_colours_or_font_sizes():
    pattern = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|font-size\s*[:=]|color:\s*white")
    for name in UI_FILES:
        for n, line in enumerate((ROOT / name).read_text().splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            assert not pattern.search(line), f"{name}:{n} hard-codes a colour/size: {line.strip()}"

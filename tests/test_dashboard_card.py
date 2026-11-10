"""The dashboard card's template must render against real spool data."""

from pathlib import Path

import yaml

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

from .test_spool_inventory import _add, _setup

CARD = Path(__file__).parent.parent / "dashboard" / "inventory_card.yaml"


async def test_card_template_renders(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _add(hass, location="Shelf A")  # 920 g, 92 %
    await _add(
        hass,
        vendor="Fiberlogy",
        material="PLA",
        color_name="White",
        spool_weight=250,
        gross_weight=450,  # 200 g left, 20 %
    )

    content = yaml.safe_load(CARD.read_text())["content"]
    rendered = Template(content, hass).async_render()

    lines = [ln for ln in rendered.splitlines() if ln.startswith("|")]
    assert lines[0].startswith("| Spool")
    # lowest first
    assert "Fiberlogy PLA White" in lines[2] and "200 g" in lines[2] and "20%" in lines[2]
    assert "Prusament PETG Galaxy Black (Shelf A)" in lines[3] and "920 g" in lines[3]
    assert "1120 g" in rendered and "2 spools" in rendered

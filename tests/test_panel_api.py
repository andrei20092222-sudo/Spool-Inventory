"""Panel registration, static files and the websocket API used by the Filament panel."""

import json

from homeassistant.components.frontend import DATA_PANELS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.spool_inventory.const import DOMAIN

from .test_spool_inventory import _setup

PANEL = "spool-inventory"


async def _subscribe(client):
    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    result = await client.receive_json()
    assert result["success"], result
    event = await client.receive_json()
    assert event["type"] == "event"
    return event["event"]


async def _next_event(client):
    msg = await client.receive_json()
    assert msg["type"] == "event", msg
    return msg["event"]


async def test_panel_registered_and_removed(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    panel = hass.data[DATA_PANELS][PANEL]
    assert panel.sidebar_title == "Filament"
    assert panel.sidebar_icon == "mdi:printer-3d-nozzle"
    assert panel.require_admin is False
    assert panel.config["_panel_custom"]["name"] == "spool-inventory-panel"
    assert panel.config["_panel_custom"]["module_url"].startswith("/spool_inventory_static/panel.js")
    # what panel.js reads as this._panel.config
    assert panel.config["static_url"] == "/spool_inventory_static"
    assert panel.config["version"]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert PANEL not in hass.data[DATA_PANELS]


async def test_static_files_are_served(hass: HomeAssistant, hass_client) -> None:
    await _setup(hass)
    client = await hass_client()

    resp = await client.get("/spool_inventory_static/panel.js")
    assert resp.status == 200
    assert "spool-inventory-panel" in await resp.text()

    resp = await client.get("/spool_inventory_static/catalog.json")
    assert resp.status == 200
    catalog = json.loads(await resp.text())
    names = [v["name"] for v in catalog["vendors"]]
    assert names[:7] == ["Prusament", "AzureFilm", "Polymaker", "Rosa3D", "Raise3D", "Elegoo", "Buddy3D"]
    assert len(names) > 100 and len(set(names)) == len(names)
    assert names[7:] == sorted(names[7:], key=str.lower)
    # product families the database marks with a parent brand are lines of that brand, not brands
    for family in ("PolyFlex", "PolyLite", "Panchroma", "Fiberon", "PrimaSelect", "EasyPrint", "Jessie", "The Filament"):
        assert family not in names, family
    poly = {r["line"] for rows in catalog["catalog"]["Polymaker"].values() for r in rows}
    assert {"PolyFlex 95A", "Panchroma Matte", "PolyLite", "Fiberon CF 08"} & poly >= {"PolyFlex 95A", "Panchroma Matte", "PolyLite"}
    # no junk lines made only of symbols/digits, no single-letter colors, no duplicate (line, color) pairs
    for vendor, mats in catalog["catalog"].items():
        for material, rows in mats.items():
            keys = [(r["line"].lower(), r["name"].lower()) for r in rows]
            assert len(keys) == len(set(keys)), (vendor, material)
            for r in rows:
                assert len(r["name"]) >= 2 and any(c.isalnum() for c in r["line"] or "x"), (vendor, material, r)
    assert {"PLA", "PETG", "ABS", "ASA", "TPU", "PC", "PA6"} <= set(catalog["materials"])
    assert sum(len(r) for m in catalog["catalog"].values() for r in m.values()) > 10000
    cat = catalog["catalog"]

    def has(vendor, material, line, name):
        return any(c["line"] == line and c["name"] == name for c in cat[vendor][material])

    # items that were reported missing
    assert has("AzureFilm", "PETG", "Pearl", "Red")
    assert has("Polymaker", "TPU", "PolyFlex 95A", "Black")
    assert has("Polymaker", "PLA", "PolyTerra", "Charcoal Black")
    assert has("Prusament", "PETG", "", "Emerald Green") and has("Prusament", "PETG", "", "Noctua Beige")
    assert has("Prusament", "PETG", "", "Noctua Brown") and has("Prusament", "ASA", "", "Jet Black")
    assert has("Prusament", "PC", "", "Space Grade Black") and has("AzureFilm", "ASA", "Original", "Black")
    assert has("Polymaker", "PC", "PolyMax", "Black")
    assert has("Elegoo", "PLA", "", "Black") and has("Buddy3D", "PETG", "", "Black")
    # no repeated (line, color) pair and no case-only duplicate lines anywhere
    for vendor, mats in cat.items():
        for material, rows in mats.items():
            keys = [(c["line"].lower(), c["name"].lower()) for c in rows]
            assert len(keys) == len(set(keys)), (vendor, material)
            lines = list(dict.fromkeys(c["line"] for c in rows))
            assert len({line.lower() for line in lines}) == len(lines), (vendor, material)
            # lines are grouped (each line's colors are contiguous), standard line first
            assert [c["line"] for c in rows] == sorted((c["line"] for c in rows), key=lines.index)
            assert lines[0] == rows[0]["line"]
    prusament = {c["name"]: c for c in catalog["catalog"]["Prusament"]["PETG"]}
    assert prusament["Pistachio Green"]["hex"] == "#93a683"
    assert prusament["Prusa Galaxy Black"]["hex"] == "#3d3e3d"
    assert [c["name"] for c in catalog["catalog"]["Raise3D"]["PETG ESD"]] == ["Black"]
    assert "ESD" in "".join(catalog["catalog"]["Polymaker"])  # Polymaker's ESD lives under PETG ESD
    assert not any(
        isinstance(c["hex"], str) is False or len(c["hex"]) != 7
        for mats in catalog["catalog"].values()
        for rows in mats.values()
        for c in rows
    )


async def test_websocket_full_cycle(hass: HomeAssistant, hass_ws_client) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)

    first = await _subscribe(client)
    assert first["spools"] == []

    # add from a scale reading
    await client.send_json_auto_id(
        {
            "type": f"{DOMAIN}/add",
            "vendor": "Prusament",
            "material": "PETG",
            "product": "",
            "color_name": "Pistachio Green",
            "color": "#93A683",
            "initial_weight": 1000,
            "spool_weight": 201,
            "gross_weight": 742,
            "location": "Bedroom shelf",
        }
    )
    added = None
    for _ in range(2):  # the result and the pushed event arrive in either order
        msg = await client.receive_json()
        if msg["type"] == "result":
            assert msg["success"], msg
            added = msg["result"]
        else:
            pushed = msg["event"]
    assert added["remaining_weight"] == 541.0
    assert added["color_hex"] == "#93a683"
    assert added["name"] == "Prusament PETG Pistachio Green"
    assert pushed["spools"][0]["id"] == added["id"]
    assert pushed["summary"]["total_remaining"] == 541.0

    entity_id = "sensor.prusament_petg_pistachio_green"
    assert float(hass.states.get(entity_id).state) == 541.0

    # a second spool of the same color; summary exposes grams per spool and per color
    await client.send_json_auto_id(
        {"type": f"{DOMAIN}/add", "vendor": "Fiberlogy", "material": "PETG",
         "color_name": "Pistachio Green", "remaining_weight": 300}
    )
    await client.receive_json()
    await client.receive_json()
    total = hass.states.get("sensor.spool_inventory_total_filament")
    assert float(total.state) == 841.0
    assert total.attributes["breakdown"] == {
        "Fiberlogy PETG Pistachio Green": 300.0,
        "Prusament PETG Pistachio Green": 541.0,
    }
    assert total.attributes["by_color"] == {"PETG Pistachio Green": 841.0}

    # update, weigh, consume
    for payload, expected in (
        ({"type": f"{DOMAIN}/update", "spool_id": added["id"], "remaining_weight": 400,
          "color_name": "Mint"}, 400.0),
        ({"type": f"{DOMAIN}/weigh", "spool_id": added["id"], "gross_weight": 601}, 400.0),
        ({"type": f"{DOMAIN}/consume", "spool_id": added["id"], "grams": 50.5}, 349.5),
    ):
        await client.send_json_auto_id(payload)
        results = [await client.receive_json() for _ in range(2)]
        res = next(m for m in results if m["type"] == "result")
        assert res["success"], res
        assert res["result"]["remaining_weight"] == expected

    # renamed spool: sensor state follows, device name follows
    state = hass.states.get(entity_id)
    assert state.attributes["name"] == "Prusament PETG Mint"
    device_id = er.async_get(hass).async_get(entity_id).device_id
    assert dr.async_get(hass).async_get(device_id).name == "Prusament PETG Mint"

    # delete removes sensor, entity registry entry and device
    await client.send_json_auto_id({"type": f"{DOMAIN}/delete", "spool_id": added["id"]})
    results = [await client.receive_json() for _ in range(2)]
    assert next(m for m in results if m["type"] == "result")["success"]
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) is None
    assert er.async_get(hass).async_get(entity_id) is None
    assert dr.async_get(hass).async_get(device_id) is None
    assert hass.states.get("sensor.spool_inventory_spool_count").state == "1"


async def test_websocket_errors_are_reported(hass: HomeAssistant, hass_ws_client) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)

    # scale reading below the empty spool weight
    await client.send_json_auto_id(
        {"type": f"{DOMAIN}/add", "vendor": "X", "material": "PETG", "spool_weight": 200, "gross_weight": 100}
    )
    msg = await client.receive_json()
    assert not msg["success"]
    assert "lower than the empty spool weight" in msg["error"]["message"]

    # both weights given
    await client.send_json_auto_id(
        {"type": f"{DOMAIN}/add", "vendor": "X", "material": "PETG", "remaining_weight": 1, "gross_weight": 5}
    )
    assert not (await client.receive_json())["success"]

    # invalid color / unknown spool / missing fields
    await client.send_json_auto_id({"type": f"{DOMAIN}/add", "vendor": "X", "material": "PETG", "color": "nope"})
    assert not (await client.receive_json())["success"]
    await client.send_json_auto_id({"type": f"{DOMAIN}/consume", "spool_id": "missing", "grams": 1})
    msg = await client.receive_json()
    assert not msg["success"] and "missing" in msg["error"]["message"]
    await client.send_json_auto_id({"type": f"{DOMAIN}/add", "material": "PETG"})
    assert not (await client.receive_json())["success"]
    assert hass.states.get("sensor.spool_inventory_spool_count").state == "0"


async def test_non_admin_can_view_but_not_change(
    hass: HomeAssistant, hass_ws_client, hass_read_only_access_token
) -> None:
    await _setup(hass)
    admin = await hass_ws_client(hass)
    await admin.send_json_auto_id(
        {"type": f"{DOMAIN}/add", "vendor": "Prusament", "material": "PETG", "color_name": "Black"}
    )
    await admin.receive_json()
    await admin.receive_json() if False else None

    viewer = await hass_ws_client(hass, hass_read_only_access_token)
    event = await _subscribe(viewer)
    assert len(event["spools"]) == 1
    spool_id = event["spools"][0]["id"]

    for payload in (
        {"type": f"{DOMAIN}/add", "vendor": "X", "material": "PETG"},
        {"type": f"{DOMAIN}/update", "spool_id": spool_id, "location": "x"},
        {"type": f"{DOMAIN}/consume", "spool_id": spool_id, "grams": 1},
        {"type": f"{DOMAIN}/delete", "spool_id": spool_id},
    ):
        await viewer.send_json_auto_id(payload)
        msg = await viewer.receive_json()
        assert not msg["success"] and msg["error"]["code"] == "unauthorized", msg
    assert hass.states.get("sensor.spool_inventory_spool_count").state == "1"


async def test_subscription_pushes_changes_made_elsewhere(hass: HomeAssistant, hass_ws_client) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)
    await _subscribe(client)

    await hass.services.async_call(
        DOMAIN, "add_spool", {"vendor": "Polymaker", "material": "PETG", "color_name": "Teal"}, blocking=True
    )
    event = await _next_event(client)
    assert [s["name"] for s in event["spools"]] == ["Polymaker PETG Teal"]

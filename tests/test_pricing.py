"""Price calculator (v1.1.0)."""

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.spool_inventory.const import DOMAIN
from custom_components.spool_inventory.pricing import calculate

from .test_spool_inventory import _setup

RATES = {"energy_cost": 1.2, "labor_rate": 40, "failure_pct": 5}
MACHINE = {"price": 5700, "service": 3000, "life_hours": 10000, "kwh_per_h": 0.24}
JOB = {
    "hours": 8 + 31 / 60, "prep_min": 5, "post_min": 3,
    "filaments": [{"grams": 106, "price_per_kg": 170}],
}


def test_matches_the_spreadsheet_it_was_modelled_on() -> None:
    r = calculate(RATES, MACHINE, JOB)
    assert r["filament"] == 18.02
    assert r["electricity"] == pytest.approx(2.45, abs=0.005)
    assert r["depreciation"] == pytest.approx(7.41, abs=0.005)
    assert r["preparation"] == 3.33 and r["post_processing"] == 2.0
    assert r["subtotal"] == pytest.approx(33.22, abs=0.01)
    assert r["with_failures"] == pytest.approx(34.88, abs=0.01)
    assert r["suggested_pct"] == 35 and r["suggested"] == pytest.approx(47.08, abs=0.01)
    assert r["markup_price"] == pytest.approx(40.11, abs=0.01)
    assert r["profit"] is None  # nothing quoted yet


def test_big_jobs_get_the_smaller_markup_and_profit_is_shown() -> None:
    r = calculate({**RATES, "markup_large_pct": 20}, None, {"design": 200, "quoted": 300, "shipping": 15})
    assert r["with_failures"] == 210 and r["suggested_pct"] == 20 and r["suggested"] == 252
    assert r["total"] == 315 and r["profit"] == 90


def test_nonsense_input_is_harmless() -> None:
    r = calculate({}, {"price": 1, "life_hours": 0}, {"hours": "abc", "filaments": ["x", {"grams": -5, "price_per_kg": "nan"}], "extra": None})
    assert r["subtotal"] == 0 and r["depreciation"] == 0


async def test_machines_quotes_and_backup_round_trip(hass: HomeAssistant) -> None:
    m = (await _setup(hass)).runtime_data
    pr = m.pricing
    pr.update_settings(RATES)
    machine = pr.machine_add({"name": "Core One+", **MACHINE})
    assert pr.payload()["machines"][0]["depreciation_per_h"] == 0.87
    q = pr.quote_save({"customer": "Test", "description": "Moss pole", "machine_id": machine["id"], **JOB, "quoted": 50})
    assert q["result"]["profit"] == pytest.approx(15.12, abs=0.01) and q["status"] == "draft"
    q2 = pr.quote_save({**q, "status": "paid"}, q["id"])
    assert len(pr.quotes) == 1 and q2["status"] == "paid" and q2["created"] == q["created"]
    # a changed rate re-prices the shown result
    pr.update_settings({"labor_rate": 80})
    assert pr.quotes[0]["result"]["preparation"] == 6.67
    # it survives a backup and a restore
    data = m.export_data()
    assert data["pricing"]["machines"][0]["name"] == "Core One+"
    pr.quote_delete(q["id"])
    pr.machine_delete(machine["id"])
    assert pr.quotes == [] and pr.machines == []
    await m.async_import(data, replace=True)
    assert len(pr.quotes) == 1 and pr.machines[0]["name"] == "Core One+" and pr.settings["energy_cost"] == 1.2
    await m.async_import(data, replace=False)  # merging again adds nothing twice
    assert len(pr.quotes) == 1 and len(pr.machines) == 1


async def test_errors(hass: HomeAssistant) -> None:
    pr = (await _setup(hass)).runtime_data.pricing
    for call in (lambda: pr.machine_delete("x"), lambda: pr.quote_delete("x"), lambda: pr.quote_save({}, "x"), lambda: pr.machine_update("x", {})):
        with pytest.raises(ServiceValidationError):
            call()
    for i in range(10):
        pr.machine_add({"name": f"M{i}"})
    with pytest.raises(ServiceValidationError):
        pr.machine_add({"name": "one too many"})


async def test_websocket(hass: HomeAssistant, hass_ws_client, hass_read_only_access_token) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)

    async def call(payload):
        await client.send_json_auto_id({**payload})
        while (msg := await client.receive_json())["type"] == "event":
            pass  # changes are pushed to the subscription; the answer is the next "result"
        return msg

    r = await call({"type": f"{DOMAIN}/pricing_settings", **RATES})
    assert r["success"]
    r = await call({"type": f"{DOMAIN}/machine_add", "name": "Core One+", **MACHINE})
    mid = r["result"]["id"]
    r = await call({"type": f"{DOMAIN}/price_calc", "machine_id": mid, "hours": 2, "filaments": [{"grams": 100, "price_per_kg": 100}]})
    assert r["result"]["filament"] == 10.0 and r["result"]["depreciation"] == 1.74
    r = await call({"type": f"{DOMAIN}/quote_save", "customer": "A", "machine_id": mid, "hours": 1, "quoted": 20})
    assert r["success"]
    qid = r["result"]["id"]
    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    await client.receive_json()
    event = await client.receive_json()
    assert event["event"]["pricing"]["quotes"][0]["id"] == qid
    r = await call({"type": f"{DOMAIN}/quote_save", "quote_id": "nope"})
    assert not r["success"]
    r = await call({"type": f"{DOMAIN}/quote_delete", "quote_id": qid})
    assert r["success"]
    r = await call({"type": f"{DOMAIN}/price_calc", "hours": -1})
    assert not r["success"]  # out of range is refused


async def test_non_admin_can_calculate_but_not_save(hass: HomeAssistant, hass_ws_client, hass_read_only_access_token) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json_auto_id({"type": f"{DOMAIN}/price_calc", "hours": 1})
    assert (await client.receive_json())["success"]
    await client.send_json_auto_id({"type": f"{DOMAIN}/quote_save"})
    assert not (await client.receive_json())["success"]


async def test_customer_list(hass: HomeAssistant) -> None:
    m = (await _setup(hass)).runtime_data
    pr = m.pricing
    assert pr.customer_add("  Alex ") == ["Alex"]
    assert pr.customer_add("alex") == ["Alex"]  # same name, different case: not added twice
    pr.customer_add("Sam")
    # a quote for a new name puts it on the list, an existing name stays as it is
    q = pr.quote_save({"customer": "Robin", "description": "Stand"})
    pr.quote_save({"customer": "alex"})
    assert pr.payload()["customers"] == ["Alex", "Robin", "Sam"]
    # renaming also changes the saved quotes; the new name may not clash with another one
    pr.customer_rename("Robin", "Robin B")
    assert next(x for x in pr.quotes if x["id"] == q["id"])["customer"] == "Robin B"
    with pytest.raises(ServiceValidationError):
        pr.customer_rename("Sam", "alex")
    with pytest.raises(ServiceValidationError):
        pr.customer_rename("Nobody", "X")
    # removing a name keeps what is written on the quotes
    pr.customer_delete("Robin B")
    assert "Robin B" not in pr.customers and any(x["customer"] == "Robin B" for x in pr.quotes)
    with pytest.raises(ServiceValidationError):
        pr.customer_delete("Robin B")
    with pytest.raises(ServiceValidationError):
        pr.customer_add("   ")
    # backup, restore and merge
    data = m.export_data()
    assert data["pricing"]["customers"] == ["Alex", "Sam"]
    await m.async_import(data, replace=True)
    assert pr.customers == ["Alex", "Sam"]
    pr.customer_delete("Sam")
    await m.async_import(data, replace=False)
    assert pr.customers == ["Alex", "Sam"]  # merge brings missing names back, no duplicates


async def test_customer_websocket(hass: HomeAssistant, hass_ws_client) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)
    for payload, ok in (
        ({"type": f"{DOMAIN}/customer_add", "name": "Alex"}, True),
        ({"type": f"{DOMAIN}/customer_rename", "name": "Alex", "new_name": "Alexandru"}, True),
        ({"type": f"{DOMAIN}/customer_rename", "name": "Nope", "new_name": "X"}, False),
        ({"type": f"{DOMAIN}/customer_add", "name": ""}, False),
        ({"type": f"{DOMAIN}/customer_delete", "name": "Alexandru"}, True),
    ):
        await client.send_json_auto_id(payload)
        assert (await client.receive_json())["success"] is ok, payload

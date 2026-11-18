"""Automatic subtraction from PrusaLink prints (v0.11.0)."""

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.spool_inventory.prusalink_usage import PrusaLinkTracker

from .test_features import _add
from .test_spool_inventory import _setup


class FakeClient:
    def __init__(self, grams=40.0, job_id=7, fail=False, meta=None):
        self.job = {"id": job_id, "progress": 0, "file": {"name": "BOX~1.BGC", "display_name": "box.bgcode", "path": "/usb/box", "refs": {"download": "/usb/box.bgcode"}}}
        self.meta = meta if meta is not None else {"filament_used_g": grams}
        self.fail = fail

    async def get_job(self):
        return self.job



async def _printer(hass: HomeAssistant, client: FakeClient):
    entry = await _setup(hass)
    m = entry.runtime_data
    pl = MockConfigEntry(domain="prusalink", data={"host": "x", "username": "maker", "password": "p"})
    pl.add_to_hass(hass)
    reg = er.async_get(hass)
    state = reg.async_get_or_create("sensor", "prusalink", f"{pl.entry_id}_printer.state", config_entry=pl, suggested_object_id="core_one")
    prog = reg.async_get_or_create("sensor", "prusalink", f"{pl.entry_id}_job.progress", config_entry=pl, suggested_object_id="core_one_progress")
    m.settings["prusalink_auto"] = True
    async def read_meta(self, eid, ref):
        if client.fail:
            raise RuntimeError("boom")
        return client.meta

    p1 = patch.object(PrusaLinkTracker, "_client", lambda self, eid: client)
    p2 = patch.object(PrusaLinkTracker, "_read_meta", read_meta)
    p1.start()
    p2.start()

    class _Both:
        @staticmethod
        def stop():
            p1.stop()
            p2.stop()

    return m, state.entity_id, prog.entity_id, _Both


async def test_finished_print_subtracts_full_estimate(hass: HomeAssistant) -> None:
    m, st, pg, patcher = await _printer(hass, FakeClient(40.0))
    try:
        a = await _add(hass, "Galaxy Black", remaining_weight=800)
        m.async_update(a, {"loaded": True})
        hass.states.async_set(st, "idle")
        hass.states.async_set(st, "printing")
        await hass.async_block_till_done()
        assert m.auto_jobs and m.get(a).remaining_weight == 800
        hass.states.async_set(pg, "60")
        hass.states.async_set(st, "finished")
        await hass.async_block_till_done()
        assert m.get(a).remaining_weight == 760
        row = m.history(a)[0]
        assert row["action"] == "used" and row["note"] == "auto: box.bgcode, 40 g, estimate"
        assert (row["before"], row["after"]) == (800, 760) and not m.auto_jobs
        # the same state again (or the printer going idle) never bills twice
        hass.states.async_set(st, "idle")
        await hass.async_block_till_done()
        assert m.get(a).remaining_weight == 760
    finally:
        patcher.stop()


async def test_cancelled_print_subtracts_share(hass: HomeAssistant) -> None:
    m, st, pg, patcher = await _printer(hass, FakeClient(100.0))
    try:
        a = await _add(hass, "Galaxy Black", remaining_weight=500)
        m.async_update(a, {"loaded": True})
        hass.states.async_set(st, "printing")
        await hass.async_block_till_done()
        hass.states.async_set(pg, "25")
        hass.states.async_set(st, "paused")  # a pause keeps following the same print
        hass.states.async_set(st, "printing")
        await hass.async_block_till_done()
        hass.states.async_set(st, "stopped")
        await hass.async_block_till_done()
        assert m.get(a).remaining_weight == 475
        assert "stopped at 25%" in m.history(a)[0]["note"]
    finally:
        patcher.stop()


async def test_missed_finished_state_uses_progress(hass: HomeAssistant) -> None:
    m, st, pg, patcher = await _printer(hass, FakeClient(30.0))
    try:
        a = await _add(hass, "Galaxy Black", remaining_weight=500)
        m.async_update(a, {"loaded": True})
        hass.states.async_set(st, "printing")
        await hass.async_block_till_done()
        hass.states.async_set(pg, "100")
        hass.states.async_set(st, "idle")  # the 30 s poll skipped "finished"
        await hass.async_block_till_done()
        assert m.get(a).remaining_weight == 470
    finally:
        patcher.stop()


async def test_off_by_default_does_nothing(hass: HomeAssistant) -> None:
    m, st, pg, patcher = await _printer(hass, FakeClient(40.0))
    try:
        m.settings["prusalink_auto"] = False
        a = await _add(hass, "Galaxy Black", remaining_weight=500)
        m.async_update(a, {"loaded": True})
        hass.states.async_set(st, "printing")
        hass.states.async_set(st, "finished")
        await hass.async_block_till_done()
        assert m.get(a).remaining_weight == 500 and not m.auto_jobs
    finally:
        patcher.stop()


async def test_unreadable_file_notifies_and_changes_nothing(hass: HomeAssistant) -> None:
    m, st, pg, patcher = await _printer(hass, FakeClient(fail=True))
    try:
        a = await _add(hass, "Galaxy Black", remaining_weight=500)
        m.async_update(a, {"loaded": True})
        hass.states.async_set(st, "printing")
        await hass.async_block_till_done()
        hass.states.async_set(st, "finished")
        await hass.async_block_till_done()
        assert m.get(a).remaining_weight == 500
        notes = hass.data["persistent_notification"]
        assert any("could not read the file" in n["message"] for n in notes.values())
    finally:
        patcher.stop()


async def test_no_loaded_spool_then_marked_before_end(hass: HomeAssistant) -> None:
    m, st, pg, patcher = await _printer(hass, FakeClient(20.0))
    try:
        a = await _add(hass, "Galaxy Black", remaining_weight=500)
        hass.states.async_set(st, "printing")
        await hass.async_block_till_done()
        assert any("no single spool" in n["message"] for n in hass.data["persistent_notification"].values())
        m.async_update(a, {"loaded": True})
        hass.states.async_set(st, "finished")
        await hass.async_block_till_done()
        assert m.get(a).remaining_weight == 480
    finally:
        patcher.stop()


async def test_length_only_file_is_converted(hass: HomeAssistant) -> None:
    m, st, pg, patcher = await _printer(hass, FakeClient(meta={"filament_used_mm": 1000.0}))
    try:
        a = await _add(hass, "Galaxy Black", remaining_weight=500, material="PETG")
        m.async_update(a, {"loaded": True})
        hass.states.async_set(st, "printing")
        await hass.async_block_till_done()
        assert abs(m.auto_jobs[next(iter(m.auto_jobs))]["grams"] - 3.06) < 0.05
    finally:
        patcher.stop()


async def test_tracking_survives_restart(hass: HomeAssistant, hass_storage) -> None:
    m, st, pg, patcher = await _printer(hass, FakeClient(40.0))
    try:
        a = await _add(hass, "Galaxy Black", remaining_weight=500)
        m.async_update(a, {"loaded": True})
        hass.states.async_set(st, "printing")
        await hass.async_block_till_done()
        await m.async_flush()
        saved = hass_storage["spool_inventory.spools"]["data"]
        assert saved["auto_jobs"] and saved["settings"]["prusalink_auto"] is True
    finally:
        patcher.stop()


async def test_numbers_from_the_job_info_need_no_download(hass: HomeAssistant) -> None:
    client = FakeClient(fail=True)  # a download would fail
    client.job["file"]["meta"] = {"filament used [g]": 12.5}
    m, st, pg, patcher = await _printer(hass, client)
    try:
        a = await _add(hass, "Galaxy Black", remaining_weight=500)
        m.async_update(a, {"loaded": True})
        hass.states.async_set(st, "printing")
        await hass.async_block_till_done()
        hass.states.async_set(st, "finished")
        await hass.async_block_till_done()
        assert m.get(a).remaining_weight == 487.5
    finally:
        patcher.stop()


async def test_file_appears_a_few_seconds_after_the_print_starts(hass: HomeAssistant) -> None:
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    client = FakeClient(25.0)
    real_job = client.job
    client.job = None  # the printer does not report the file yet
    m, st, pg, patcher = await _printer(hass, client)
    try:
        a = await _add(hass, "Galaxy Black", remaining_weight=500)
        m.async_update(a, {"loaded": True})
        hass.states.async_set(st, "printing")
        await hass.async_block_till_done()
        assert m.auto_jobs and next(iter(m.auto_jobs.values()))["grams"] is None
        assert not hass.data.get("persistent_notification")  # no alarm yet
        client.job = real_job  # a few seconds later the file shows up
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=15))
        await hass.async_block_till_done()
        assert next(iter(m.auto_jobs.values()))["grams"] == 25.0
        hass.states.async_set(st, "finished")
        await hass.async_block_till_done()
        assert m.get(a).remaining_weight == 475
    finally:
        patcher.stop()


async def test_gives_up_after_the_last_try_and_says_so(hass: HomeAssistant) -> None:
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    from custom_components.spool_inventory.prusalink_usage import RETRY_DELAYS

    client = FakeClient(fail=True)
    m, st, pg, patcher = await _printer(hass, client)
    try:
        a = await _add(hass, "Galaxy Black", remaining_weight=500)
        m.async_update(a, {"loaded": True})
        hass.states.async_set(st, "printing")
        await hass.async_block_till_done()
        for _ in RETRY_DELAYS:
            assert not hass.data.get("persistent_notification")
            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=130))
            await hass.async_block_till_done()
        msgs = [n["message"] for n in hass.data["persistent_notification"].values()]
        assert any("could not read the file" in t for t in msgs), f"Expected file read error notification not found. Actual messages: {msgs}"
        hass.states.async_set(st, "finished")
        await hass.async_block_till_done()
        assert m.get(a).remaining_weight == 500
    finally:
        patcher.stop()


async def _material(hass, m, st):
    pl = hass.config_entries.async_entries("prusalink")[0]
    reg = er.async_get(hass)
    return reg.async_get_or_create("sensor", "prusalink", f"{pl.entry_id}_printer.telemetry.material", config_entry=pl, suggested_object_id="core_one_material").entity_id


async def test_unloading_clears_the_loaded_spool(hass: HomeAssistant) -> None:
    m, st, pg, patcher = await _printer(hass, FakeClient())
    try:
        mat = await _material(hass, m, st)
        a = await _add(hass, "Galaxy Black", remaining_weight=500)
        b = await _add(hass, "Other", remaining_weight=500)
        m.async_update(a, {"loaded": True})
        m.settings["prusalink_unload"] = True
        hass.states.async_set(st, "idle")
        hass.states.async_set(mat, "unavailable")  # printer off: nothing happens
        hass.states.async_set(mat, "PETG")
        await hass.async_block_till_done()
        hass.states.async_set(mat, "unavailable")  # switched off again
        hass.states.async_set(mat, "---")
        await hass.async_block_till_done()
        assert m.get(a).loaded  # unavailable -> --- is not an unload
        hass.states.async_set(mat, "PETG")
        await hass.async_block_till_done()
        hass.states.async_set(mat, "---")  # a real unload
        await hass.async_block_till_done()
        assert not m.get(a).loaded and not m.get(b).loaded
        assert m.history(a)[0]["action"] == "unloaded"
    finally:
        patcher.stop()


async def test_unload_is_ignored_while_printing_or_when_switched_off(hass: HomeAssistant) -> None:
    m, st, pg, patcher = await _printer(hass, FakeClient())
    try:
        mat = await _material(hass, m, st)
        a = await _add(hass, "Galaxy Black", remaining_weight=500)
        m.async_update(a, {"loaded": True})
        # switched off (the default)
        hass.states.async_set(mat, "PETG")
        hass.states.async_set(mat, "---")
        await hass.async_block_till_done()
        assert m.get(a).loaded
        # switched on, but a print is running (a filament runout must not clear the spool)
        m.settings["prusalink_unload"] = True
        m.settings["prusalink_auto"] = False
        hass.states.async_set(st, "printing")
        hass.states.async_set(mat, "PETG")
        hass.states.async_set(mat, "---")
        await hass.async_block_till_done()
        assert m.get(a).loaded
    finally:
        patcher.stop()

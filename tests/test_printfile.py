"""Reading the filament estimate from .gcode and .bgcode files (v0.11.0)."""

import struct
import zlib

import httpx
import pytest

from custom_components.spool_inventory.printfile import PrintFileError, parse_bgcode, stream_estimate

STATS = (
    "; filament used [mm] = 3632.86\n; filament used [g] = 11.27\n; filament cost = 0.25\n"
    "; filament used [cm3] = 8.74\n; total filament used for wipe tower [g] = 0.00\n"
    "; estimated printing time (normal mode) = 25m 9s\n\n;\n"
)


def _block(btype, payload, *, compress=False, params=b"\x00\x00"):
    data = zlib.compress(payload) if compress else payload
    head = struct.pack("<HHI", btype, 1 if compress else 0, len(payload))
    if compress:
        head += struct.pack("<I", len(data))
    return head + params + data + b"\x00\x00\x00\x00"  # CRC is not checked by the reader


def bgcode(meta="filament used [mm]=3632.86\nfilament used [g]=11.27\nfilament_type=PETG\n", *, gcode_size=5_000_000):
    out = b"GCDE" + struct.pack("<IH", 1, 1)
    out += _block(0, b"Producer=PrusaSlicer 2.9\n")
    out += _block(3, b"printer_model=COREONE\n" + meta.encode(), compress=True)
    out += _block(5, b"\x89PNG" + b"x" * 40_000, params=struct.pack("<HHH", 0, 16, 16))
    out += _block(4, b"estimated printing time (normal mode)=25m 9s\n")
    out += struct.pack("<HHI", 1, 0, gcode_size) + b"\x00\x00"  # start of the G-code block
    return out


def _client(body: bytes, status=200, chunk=7000):
    seen = {"bytes": 0}

    async def stream():
        for i in range(0, len(body), chunk):
            seen["bytes"] += len(body[i : i + chunk])
            yield body[i : i + chunk]

    transport = httpx.MockTransport(lambda req: httpx.Response(status, content=stream()))
    return httpx.AsyncClient(transport=transport), seen


async def test_text_gcode_reads_the_footer() -> None:
    body = b"G1 X1 Y1\n" * 200_000 + STATS.encode() + b"; filament_type = PETG\n"  # ~1.8 MB
    client, _ = _client(body)
    got = await stream_estimate(client, "http://p/usb/x.gcode", None)
    assert got == {"filament_used_g": 11.27, "filament_used_mm": 3632.86, "filament_type": "PETG"}


async def test_bgcode_reads_the_header_and_stops_early() -> None:
    body = bgcode() + b"\x00" * 5_000_000
    client, seen = _client(body, chunk=4096)
    got = await stream_estimate(client, "http://p/usb/x.bgcode", None)
    assert got == {"filament_used_g": 11.27, "filament_used_mm": 3632.86, "filament_type": "PETG"}
    assert seen["bytes"] < 200_000  # the 5 MB of G-code was not downloaded


async def test_bgcode_split_in_tiny_chunks() -> None:
    client, _ = _client(bgcode(), chunk=3)
    got = await stream_estimate(client, "http://p/x", None)
    assert got["filament_used_g"] == 11.27


def test_bgcode_incomplete_asks_for_more() -> None:
    raw, complete = parse_bgcode(bgcode()[:200])
    assert not complete


async def test_multi_material_is_flagged_not_guessed() -> None:
    client, _ = _client(bgcode("filament used [g]=5.1, 2.2\nfilament used [mm]=1000, 500\n"))
    got = await stream_estimate(client, "http://p/x", None)
    assert got.get("multi") is True and "filament_used_g" not in got


async def test_file_without_numbers_gives_nothing() -> None:
    client, _ = _client(b"G1 X1\n" * 1000)
    assert await stream_estimate(client, "http://p/x", None) == {}


@pytest.mark.parametrize(("status", "text"), [(401, "login"), (404, "no longer")])
async def test_printer_errors_are_explained(status, text) -> None:
    client, _ = _client(b"", status=status)
    with pytest.raises(PrintFileError, match=text):
        await stream_estimate(client, "http://p/x", None)


def test_agrees_with_the_pyprusalink_parser() -> None:
    pyprusalink = pytest.importorskip("pyprusalink.file_metadata")
    if not hasattr(pyprusalink, "parse_file_metadata"):
        pytest.skip("older library")
    data = bgcode()
    theirs = pyprusalink.parse_file_metadata(data)
    ours, _ = parse_bgcode(data)
    assert float(ours["filament used [g]"]) == theirs["filament_used_g"]
    assert float(ours["filament used [mm]"]) == theirs["filament_used_mm"]


async def test_tries_the_next_address_when_one_is_not_found(hass) -> None:
    from unittest.mock import patch

    from custom_components.spool_inventory.printfile import read_estimate

    asked = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        if request.url.path == "/api/v1/files/usb/A.BGC":
            return httpx.Response(200, content=bgcode())
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with patch("custom_components.spool_inventory.printfile.get_async_client", return_value=client):
        got = await read_estimate(hass, "http://p", "maker", "pw", ["/usb/A.BGC", "/api/v1/files/usb/A.BGC"])
        assert got["filament_used_g"] == 11.27 and asked == ["/usb/A.BGC", "/api/v1/files/usb/A.BGC"]
        with pytest.raises(PrintFileError, match=r"no filament numbers found \(/usb/A.BGC: not found; /x: not found\)"):
            await read_estimate(hass, "http://p", "maker", "pw", ["/usb/A.BGC", "/x"])


def test_estimate_from_the_job_info() -> None:
    from custom_components.spool_inventory.printfile import from_job_meta

    got = from_job_meta({"filament used [g]": 11.27, "filament used [mm]": 3632.86, "filament_type": "PETG", "other": 1})
    assert got == {"filament_used_g": 11.27, "filament_used_mm": 3632.86, "filament_type": "PETG"}
    assert from_job_meta(None) == {} and from_job_meta({}) == {}


async def test_json_reply_with_numbers_is_used(hass) -> None:
    from unittest.mock import patch

    from custom_components.spool_inventory.printfile import read_estimate

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/usb/X":
            return httpx.Response(404)
        return httpx.Response(200, json={"name": "X", "meta": {"filament used [g]": "41.2", "filament used [mm]": "13800"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with patch("custom_components.spool_inventory.printfile.get_async_client", return_value=client):
        got = await read_estimate(hass, "http://p", "u", "p", ["/usb/X", "/api/v1/files/usb/X"])
    assert got["filament_used_g"] == 41.2


async def test_failure_says_what_was_seen(hass) -> None:
    from unittest.mock import patch

    from custom_components.spool_inventory.printfile import read_estimate

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a":
            return httpx.Response(200, json={"name": "X", "meta": {"estimated printing time (normal mode)": "5h"}})
        return httpx.Response(200, content=bgcode("estimated printing time (normal mode)=5h\n"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with patch("custom_components.spool_inventory.printfile.get_async_client", return_value=client), pytest.raises(PrintFileError) as err:
        await read_estimate(hass, "http://p", "u", "p", ["/a", "/b"])
    assert "/a: file information" in str(err.value) and "/b: bgcode header without filament numbers" in str(err.value)


def test_total_keys_are_accepted_as_a_fallback() -> None:
    from custom_components.spool_inventory.printfile import to_estimate

    assert to_estimate({"total filament used [g]": "20.5"})["filament_used_g"] == 20.5
    assert to_estimate({"filament used [g]": "10", "total filament used [g]": "20.5"})["filament_used_g"] == 10


def test_file_refs_for_a_file_on_the_usb_stick():
    """The printer reports the folder in `path` and the short name in `name` (seen on a Core One+, v1.0.0)."""
    from custom_components.spool_inventory.printfile import file_refs

    job_file = {
        "refs": {"download": "/usb/PLANTH~1.BGC", "thumbnail": "/thumb/l/usb/PLANTH~1.BGC"},
        "name": "PLANTH~1.BGC",
        "display_name": "Plant Hook v1_0.4n_0.2mm_PETG_COREONE_2h59m.bgcode",
        "path": "/usb",
        "size": 0,
    }
    refs = file_refs(job_file)
    assert refs[0] == "/usb/PLANTH~1.BGC"  # the address the printer gives comes first
    assert "/api/v1/files/usb/PLANTH~1.BGC" in refs  # the file information, with the folder and the name joined
    assert len(refs) == len(set(refs))  # no address twice


def test_file_refs_when_path_already_holds_the_file():
    from custom_components.spool_inventory.printfile import file_refs

    refs = file_refs({"name": "a b.gcode", "path": "/usb/a b.gcode"})
    assert "/api/v1/files/usb/a%20b.gcode" in refs
    assert file_refs({}) == []

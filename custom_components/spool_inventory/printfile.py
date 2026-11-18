"""Read the filament estimate from a print file stored on a Prusa printer.

PrusaSlicer writes how much filament a print needs into the file itself:
  * text G-code (.gcode): comment lines near the end, e.g. "; filament used [g] = 11.27"
  * binary G-code (.bgcode, Core One / MK4 / XL): INI "metadata" blocks at the start of the file

The file is streamed from the printer so it is never held in memory as a whole. A .bgcode file
is abandoned as soon as its metadata has been read (the G-code itself comes after it), a
.gcode file is read to the end because the numbers are in the last lines.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
import struct
from typing import Any
import zlib

from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client

MAX_DOWNLOAD = 64 * 1024 * 1024  # give up on a file bigger than this
TAIL = 256 * 1024  # the numbers sit in the last lines of a .gcode file
MAX_JSON = 1024 * 1024
HEAD_MAX = 4 * 1024 * 1024  # metadata of a .bgcode file is far smaller than this
_MAGIC = b"GCDE"
_KEYS = (
    "filament used [g]", "filament used [mm]", "filament used [cm3]", "filament_type",
    "total filament used [g]", "total filament used [mm]",
)
_LINE = re.compile(r"^;?\s*([A-Za-z_ \[\]0-9()]+?)\s*=\s*(.+?)\s*$")


class PrintFileError(Exception):
    """The file could not be read or understood."""


class FileNotFound(PrintFileError):
    """The printer answered "not found" for this address."""


def _lines(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if (m := _LINE.match(line.strip())) and (key := m.group(1).strip().lower()) in _KEYS:
            out[key] = m.group(2)
    return out


def _number(value: str | None) -> float | None:
    """One number; None when missing or when there is one per tool (multi-material)."""
    if value is None or "," in value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def to_estimate(raw: Mapping[str, str]) -> dict[str, Any]:
    """Turn the raw key/values into the numbers we use."""
    out: dict[str, Any] = {}
    for keys, name in (
        (("filament used [g]", "total filament used [g]"), "filament_used_g"),
        (("filament used [mm]", "total filament used [mm]"), "filament_used_mm"),
    ):
        for key in keys:
            if (n := _number(raw.get(key))) is not None:
                out[name] = n
                break
    if any("," in raw.get(k, "") for k in _KEYS if k != "filament_type"):
        out["multi"] = True
    if raw.get("filament_type"):
        out["filament_type"] = raw["filament_type"]
    return out


def from_job_meta(meta: Mapping[str, Any] | None) -> dict[str, Any]:
    """The estimate the printer itself reports with the job (no download needed)."""
    raw = {str(k).strip().lower(): str(v).strip() for k, v in (meta or {}).items()}
    return to_estimate({k: v for k, v in raw.items() if k in _KEYS})


def parse_bgcode(data: bytes) -> tuple[dict[str, str], bool]:
    """Raw metadata from the start of a binary G-code file.

    Returns (metadata, complete). complete is False when more bytes are needed.
    """
    if len(data) < 10:
        return {}, False
    checksum = 4 if struct.unpack_from("<H", data, 8)[0] == 1 else 0
    pos = 10
    raw: dict[str, str] = {}
    while True:
        if pos + 8 > len(data):
            return raw, False
        btype, comp, size = struct.unpack_from("<HHI", data, pos)
        if btype == 1:  # the G-code itself: everything useful came before it
            return raw, True
        head = 8
        data_size = size
        if comp != 0:
            if pos + 12 > len(data):
                return raw, False
            data_size = struct.unpack_from("<I", data, pos + 8)[0]
            head = 12
        params = 6 if btype == 5 else 2  # thumbnails have 6 parameter bytes, the rest 2
        end = pos + head + params + data_size + checksum
        if end > len(data):
            return raw, False
        if btype in (0, 2, 3, 4) and struct.unpack_from("<H", data, pos + head)[0] == 0:
            block = data[pos + head + params : pos + head + params + data_size]
            try:
                text = zlib.decompress(block).decode("utf-8", "ignore") if comp == 1 else block.decode("utf-8", "ignore") if comp == 0 else ""
            except zlib.error:
                text = ""
            for line in text.splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    if (k := k.strip().lower()) in _KEYS:
                        raw[k] = v.strip()
                    elif "filament" in k:  # remembered only to explain a failure
                        raw["_other"] = (raw.get("_other", "") + "|" + k)[:200]
        pos = end


async def read_estimate(
    hass: HomeAssistant, base_url: str, username: str, password: str, paths: list[str]
) -> dict[str, Any]:
    """Stream the file from the printer and return its filament estimate.

    `paths` are the places the file may be served from (the printer reports one, firmware
    versions differ); the next one is tried when a path gives "not found".
    """
    try:
        from pyprusalink.client import DigestAuthWorkaround as Auth  # noqa: PLC0415
    except ImportError:  # pragma: no cover - older/newer library layouts
        from httpx import DigestAuth as Auth  # noqa: PLC0415
    client = get_async_client(hass)
    auth = Auth(username=username, password=password)
    seen: list[str] = []
    for path in dict.fromkeys(p for p in paths if p):
        info: list[str] = []
        try:
            got = await stream_estimate(client, f"{base_url}{path}", auth, info)
        except FileNotFound:
            seen.append(f"{path}: not found")
            continue
        if "filament_used_g" in got or "filament_used_mm" in got or got.get("multi"):
            return got
        seen.append(f"{path}: {info[0] if info else 'no numbers'}")
    raise PrintFileError("no filament numbers found (" + "; ".join(seen) + ")")


async def stream_estimate(client: Any, url: str, auth: Any, info: list[str] | None = None) -> dict[str, Any]:
    """Download `url` and extract the estimate (separate from read_estimate for testing)."""
    buf = bytearray()  # the start of the file: all a .bgcode needs
    tail = b""  # the end of the file: all a .gcode needs
    total = 0
    kind: str | None = None
    async with client.stream("GET", url, auth=auth) as response:
        if response.status_code in (401, 403):
            raise PrintFileError("the printer refused the login")
        if response.status_code == 404:
            raise FileNotFound("the file is no longer on the printer")
        response.raise_for_status()
        ctype = response.headers.get("content-type", "")
        if "json" in ctype:  # file information instead of the file: look for the numbers in it
            body = (await response.aread())[:MAX_JSON]
            try:
                obj = json.loads(body)
            except ValueError:
                obj = {}
            meta = (obj.get("meta") or (obj.get("file") or {}).get("meta") if isinstance(obj, dict) else None)
            if info is not None:
                info.append("file information, no filament numbers" if not meta else "file information")
            return from_job_meta(meta)
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > MAX_DOWNLOAD:
                raise PrintFileError("the file is too big to read")
            if kind is None:
                buf += chunk
                if len(buf) < 4:
                    continue
                kind = "bgcode" if bytes(buf[:4]) == _MAGIC else "gcode"
                chunk = b""  # already in buf
                if kind == "gcode":
                    tail = bytes(buf)[-TAIL:]
                    buf = bytearray()
            if kind == "bgcode":
                buf += chunk
                raw, complete = parse_bgcode(bytes(buf))
                if complete:
                    est = to_estimate(raw)  # the rest of the file is not needed
                    if info is not None and not est:
                        info.append(f"bgcode header without filament numbers (other keys: {raw.get('_other', 'none')})")
                    return est
                if len(buf) > HEAD_MAX:
                    raise PrintFileError("no filament information found in the file")
            else:
                tail = (tail + chunk)[-TAIL:]
    raw = parse_bgcode(bytes(buf))[0] if kind == "bgcode" else _lines(tail.decode("utf-8", "ignore")) if kind else {}
    if info is not None:
        info.append(f"{kind or 'empty'} file of {total} bytes without filament numbers (other keys: {raw.get('_other', 'none')})")
    return to_estimate(raw)

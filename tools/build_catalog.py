#!/usr/bin/env python3
"""Build custom_components/spool_inventory/www/catalog.json.

Source data: the Open Filament Database (MIT licensed),
https://github.com/OpenFilamentCollective/open-filament-database
Usage: python3 -I tools/build_catalog.py /path/to/open-filament-database

The database is community data and its folders are not always tidy (the same
product line spread over several folders, product lines hidden in color names,
"(NFC)" copies of colors). This script keeps the dropdowns clean by

* mapping every database folder to ONE product line (LINES below; the order
  of the lines there is the order of the dropdown, "" = the standard product),
* cleaning color names and dropping duplicates inside a line,
* adding products that the database does not have yet (EXTRAS below; the
  color codes there are approximate, checked against the shop pages of the
  brands/retailers, and can always be changed in the dialog).

The seven brands listed in VENDORS (the ones the author uses) get hand-made product lines for PLA, PETG and
TPU (see LINES). Every other brand and material in the database is included as it is: the product line is the
database's filament name without the material word. Variants without a hex color or without a 1.75 mm size
are skipped.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

# (display name, folder in the database, short code for the badge fallback, only these materials or None)
USED = {"PLA", "PETG", "TPU"}  # what is actually printed; add more here later (they need entries in LINES)
VENDORS = [
    ("Prusament", "prusament", "PR", USED | {"ASA", "PC"}),
    ("AzureFilm", "azurefilm", "AF", USED | {"ASA"}),
    ("Polymaker", "polymaker", "PM", USED | {"PC"}),
    ("Rosa3D", "rosa3d_filaments", "R3", USED),
    ("Raise3D", None, "R3D", None),  # not in the database, see EXTRAS
    ("Elegoo", "elegoo", "EG", {"PLA", "PETG"}),
    ("Buddy3D", "buddy3d", "B3", {"PLA", "PETG"}),
]
HAND_MADE = {v[0] for v in VENDORS}
LOGO_NAMES = {  # fixed file names, so a picture dropped into www/logos/ is found
    "Prusament": "logos/prusament.png",
    "AzureFilm": "logos/azurefilm.png",
    "Polymaker": "logos/polymaker.svg",
    "Rosa3D": "logos/rosa3d_filaments.png",
    "Raise3D": "logos/raise3d.png",
    "Elegoo": "logos/elegoo.png",
    "Buddy3D": "logos/buddy3d.png",
}
WEBSITES = {"Raise3D": "https://www.raise3d.com/"}

# Generic palette for custom entries ("standard color codes").
STANDARD_COLORS = [
    ("Black", "#1c1c1c"), ("White", "#f2f2f2"), ("Grey", "#8a8d8f"),
    ("Silver", "#c0c0c0"), ("Red", "#d62718"), ("Orange", "#f26b1d"),
    ("Yellow", "#f2c500"), ("Green", "#2e9e4f"), ("Pistachio Green", "#a8d08d"),
    ("Blue", "#1f4aa8"), ("Light Blue", "#6cb4e4"), ("Purple", "#6b3fa0"),
    ("Pink", "#e87ca6"), ("Brown", "#7a4a2a"), ("Beige", "#d9c4a0"),
    ("Gold", "#c9a227"), ("Natural", "#e8dfc8"), ("Transparent", "#dfe9ee"),
]

MATERIALS = ["PETG", "PETG ESD", "PLA", "ABS", "ASA", "TPU", "PC", "PCTG", "PA", "PET", "PVA", "HIPS", "PP"]

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# ---------------------------------------------------------------------------
# database folder -> product line.  Value None = skip the folder.
# The order of the entries is the order of the lines in the dropdown.
# ---------------------------------------------------------------------------
LINES: dict[tuple[str, str], list[tuple[str, str | None]]] = {
    ("prusament", "ASA"): [("asa", "")],
    ("prusament", "PC"): [("pc", ""), ("pc_blend", "Blend"), ("pc_cf", "CF")],
    ("azurefilm", "ASA"): [("original", "Original"), ("prime", "Prime")],
    ("polymaker", "PC"): [
        ("pc", ""), ("polymax_pc", "PolyMax"), ("polylite_pc", "PolyLite"), ("polymax_pc_fr", "PolyMax FR"),
        ("pc_abs", "PC-ABS"), ("pc_pbt", "PC-PBT"),
    ],
    ("prusament", "PETG"): [
        ("petg", ""), ("@new_petg", ""), ("matte_petg", "Matte"), ("cf_petg", "CF"), ("petg_v0", "V0"),
        ("petg_magnetite", "Magnetite"), ("petg_tungsten", "Tungsten"),
    ],
    ("prusament", "PLA"): [
        ("pla", ""), ("blend_silk_pla", "Silk Blend"), ("mystic_premium_pla", "Mystic Premium"),
        ("woodfill", "Woodfill"), ("rpla", "Recycled"), ("pla_recycled", "Recycled"),
    ],
    ("prusament", "TPU"): [("tpu_95a", "95A")],

    ("azurefilm", "PETG"): [("petg", ""), ("@pearl", "Pearl")],
    ("azurefilm", "PLA"): [
        ("pla", ""), ("silk_pla", "Silk"), ("pla_matte_hs", "Matte HS"), ("prime_pla", "Prime"),
        ("glitter_pla", "Glitter"), ("pla_original", "Original"), ("wood_pla", "Wood"),
        ("@pastel", "Pastel"),
    ],
    ("azurefilm", "TPU"): [("tpu_85a", "85A"), ("tpu_tpe", "TPE")],

    ("polymaker", "PETG"): [
        ("polylite_petg", "PolyLite"), ("petg", "PolyLite"), ("polymax_petg", "PolyMax"),
        ("cf_petg", "CF"),
    ],
    ("polymaker", "PLA"): [
        ("@polyterra", "PolyTerra"), ("polylite_pla", "PolyLite"), ("polymaker_pla_pro", "PolyLite Pro"),
        ("polymax_pla", "PolyMax"), ("polysonic_pla", "PolySonic"), ("wood_pla", "PolyWood"),
        ("panchroma_pla", "Panchroma"), ("panchroma_silk_pla", "Panchroma Silk"),
        ("satin_panchroma_pla", "Panchroma Satin"), ("muted_panchroma_matte_pla", "Panchroma Muted Matte"),
        ("neon_panchroma_pla", "Panchroma Neon"), ("panchroma_glow_pla", "Panchroma Glow"),
        ("dual_panchroma_matte_pla", "Panchroma Dual Matte"), ("gradient_panchroma_pla", "Panchroma Gradient"),
        ("metallic_polylite_pla", "PolyLite Metallic"), ("metallic_polylite_silk_pla", "PolyLite Metallic Silk"),
        ("lw_polylite_pla", "LW PolyLite"), ("polylite_cf_pla", "PolyLite CF"),
        ("ht_pla", "HT"), ("ht_pla_gf", "HT GF"), ("for_production_matte_pla", "For Production Matte"),
        ("draft_pla", "Draft"), ("polycast", "PolyCast"), ("creator_special_edition_pla", "Creator Special Edition"),
        ("pla", None), ("cf_pla", None), ("glow_pla", None), ("ht_pla_pro", None), ("silk_pla", None),
    ],
    ("polymaker", "TPU"): [("@polyflex", "PolyFlex")],  # see EXTRAS: the database has no Polymaker TPU

    ("rosa3d_filaments", "PETG"): [
        ("high_speed_petg", "High Speed"),
        ("pet_g_galaxy_hs_high_speed_petg", "High Speed Galaxy"), ("pet_g_hs_high_speed_petg", "High Speed Galaxy"),
        ("pet_g_structure_hs_high_speed_petg", "High Speed Structure"),
        ("high_speed_glow_petg", "Glow"), ("pet_g_standard_neon_green_glow_in_the_dark", "Glow"),
        ("petg", "@split"),  # one folder holding several lines, see rosa_petg()
        ("pet_g_mdt", "MDT"), ("cf_petg", "CF"), ("matte_cf_petg", "Matte CF"),
    ],
    ("rosa3d_filaments", "PLA"): [
        ("silk_pla", "Silk"), ("starter_pla", "Starter"), ("pastel_pla", "Pastel"), ("galaxy_pla", "Galaxy"),
        ("magic_pla", "Magic"), ("magic_silk_pla", "Magic Silk"), ("multicolour_silk_pla", "Multicolor Silk"),
        ("rainbow_silk_pla", "Rainbow Silk"), ("speed_matt_matte_pla", "Speed Matte"),
        ("plus_prospeedimpact_pla", "ProSpeed Impact"),
        ("glow_pla", "Glow"), ("pla_starter_neon_green_glow_in_the_dark", "Glow"),
        ("lw_aero_pla", "LW Aero"), ("matte_cf_pla", "Matte CF"), ("cf_pla", "CF"),
        ("refill_pla", "ReFill"), ("refill_silk_pla", "ReFill Silk"),
        ("pla", "@split"),
    ],
    ("rosa3d_filaments", "TPU"): [
        ("rosa_flex_tpu", "@hardness:Rosa Flex"), ("rosa_flex_glow_tpu", "@hardness:Rosa Flex Glow"),
        ("impact_abrasive_uv_h2o_microbe_resistant_rosa_tpu_hardtech_83d", "HardTech+ 83D"),
        ("rosa_tpu_automotive_15_glass_fiber", "Automotive 15GF"),
    ],

    ("elegoo", "PLA"): [
        ("pla", ""), ("pla_basic", ""), ("pla_plus", "PLA Plus"), ("pla_pro", "PLA Pro"),
        ("rapid_pla_plus", "Rapid PLA Plus"), ("pla_matte", "PLA Matte"), ("silk_pla", "Silk PLA"),
        ("galaxy_pla", "Galaxy PLA"), ("pla_metallic", "PLA Metallic"), ("pla_sparkle", "PLA Sparkle"),
        ("pla_wood", "PLA Wood"), ("pla_cf", "PLA-CF"), ("pla_glow", "PLA Glow"), ("pla_marble", "PLA Marble"),
    ],
    ("elegoo", "PETG"): [
        ("petg", ""), ("petg_pro", "PETG Pro"), ("rapid_petg", "Rapid PETG"),
        ("petg_translucent", "PETG Translucent"), ("petg_cf", "PETG-CF"), ("petg_gf", "PETG-GF"),
    ],
    ("buddy3d", "PLA"): [("pla", ""), ("silk_pla", "Silk PLA"), ("glow_pla", "Glow PLA")],
    ("buddy3d", "PETG"): [("petg", "")],
}

# Products the database does not list (or lists wrongly). (vendor folder, material, key) -> (line, weights, tare, colors)
# Hex codes are approximate: matched by eye to the shop photos.
EXTRAS: dict[tuple[str, str, str], dict] = {
    ("prusament", "PETG", "@new_petg"): {  # newer Prusament PETG colors the database does not have yet
        "weights": [1000],
        "colors": [
            ("Emerald Green", "#4ba82e"),   # Škoda partnership (all3dp.com); hex = Škoda emerald green, approximate
            ("Noctua Beige", "#e7ceb4"),    # PETG released 28 Jul 2026 (noctua.at); same colors as the PLA
            ("Noctua Brown", "#653525"),
        ],
    },
    ("azurefilm", "PETG", "@pearl"): {  # AzureFilm PETG Pearl: confirmed on 3djake.com ("AzureFilm PETG Pearl Red/Blue/Green")
        "weights": [1000],
        "colors": [("Red", "#a8263c"), ("Blue", "#2f5fa8"), ("Green", "#2f8f5b")],
    },
    ("polymaker", "PLA", "@polyterra"): {  # PolyTerra PLA, 1.75 mm, 1 kg (3djake.com color list)
        "weights": [1000], "tare": 190,
        "colors": [
            ("Charcoal Black", "#2b2b2b"), ("Cotton White", "#f1efe8"), ("Fossil Grey", "#8b8d8c"),
            ("Sapphire Blue", "#2d4f8a"), ("Peanut", "#c9a27a"), ("Lava Red", "#b32a2a"),
            ("Savannah Yellow", "#e8c34a"), ("Wood Brown", "#8a6a4a"), ("Earth Brown", "#6b4a36"),
            ("Arctic Teal", "#5fa8a6"), ("Forest Green", "#3f6f4a"), ("Sunrise Orange", "#e67a35"),
            ("Candy", "#f0a6c4"), ("Sakura Pink", "#f4c2cc"), ("Lavender Purple", "#a98bc5"),
            ("Army Red", "#7a2e2e"), ("Muted Purple", "#8d7a9f"),
        ],
    },
    ("polymaker", "TPU", "@polyflex"): {  # PolyFlex TPU, 1.75 mm (3djake.com / polymaker.com); 750 g spools, HF = 1 kg
        "lines": [
            ("PolyFlex 95A", [750], [("Black", "#1f1f1f"), ("White", "#f0f0f0"), ("Yellow", "#f0c800"),
                                    ("Red", "#c8201e"), ("Blue", "#1f4aa8"), ("Orange", "#f26b1d")]),
            ("PolyFlex 90A", [750], [("Black", "#1f1f1f"), ("Grey", "#8a8d8f"), ("White", "#f0f0f0"),
                                    ("Turquoise", "#2bb5b0"), ("Clear", "#e3eaee")]),
            ("PolyFlex 95A-HF", [1000], [("White", "#f0f0f0"), ("Black", "#1f1f1f"), ("Clear", "#e3eaee")]),
        ],
    },
}

# Raise3D is not in the database. Only the product actually used is listed:
# Industrial PETG ESD, black, 1 kg (checked against Raise3D / reseller pages).
RAISE3D = {"PETG ESD": [("Black", "#1c1c1c")]}

SMALL_WORDS = {"for", "and", "of", "the", "in", "with", "to", "a", "on"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def tidy(text: str) -> str:
    """Remove trademark signs and (NFC) copies, title-case all-lowercase words."""
    text = text.replace("™", "").replace("®", "")
    text = re.sub(r"\s*\(NFC\)\s*", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" -_")
    words = [
        w.capitalize() if w.islower() and len(w) > 1 and w not in SMALL_WORDS else w
        for w in text.split(" ")
    ]
    return " ".join(words)


def strip_material(text: str, material: str) -> str:
    pattern = r"\bPET[- ]?G\b" if material.startswith("PETG") else rf"\b{re.escape(material)}\b"
    return tidy(re.sub(pattern, "", text, flags=re.I))


def generic_line(filament_name: str, material: str) -> str:
    """'PolyLite PLA' -> 'PolyLite'; 'PETG' -> ''; 'PLA+' stays 'PLA+' (stripping would leave only '+')."""
    pattern = r"\bPET[- ]?G\b" if material.startswith("PETG") else rf"\b{re.escape(material)}\b"
    stripped = strip_material(filament_name, material)
    junk = re.fullmatch(r"[\W\d_]*", stripped) is not None and stripped != ""
    glued = re.search(pattern + r"[+/]|[+/]" + pattern, filament_name, flags=re.I) is not None
    if junk or glued or re.match(r"^[-/+]", stripped):
        return tidy(filament_name)
    return stripped


def shout_to_title(text: str) -> str:
    """'BONDI BEACH' -> 'Bondi Beach'; names with digits or very short ones ('10CF', 'UV') are left alone."""
    if not text.isupper() or len(text) <= 3 or any(c.isdigit() for c in text):
        return text
    return re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), text)


def clean_color(name: str, material: str) -> str:
    """Drop the material word from a color name ('PLA Marble' -> 'Marble') and normalise shouting."""
    pattern = r"\bPET[- ]?G\b" if material.startswith("PETG") else rf"\b{re.escape(material)}\b"
    stripped = re.sub(pattern, "", name, flags=re.I)
    stripped = re.sub(r"\s+", " ", stripped).strip(" -_/")
    return shout_to_title(tidy(stripped)) if stripped else tidy(name)


# --- per-vendor fixes for messy color names -----------------------------------

def fix_color(vendor: str, material: str, folder: str, line: str, name: str) -> tuple[str, str] | None:
    """Return the final (line, color name), or None to drop the variant."""
    name = tidy(name)
    name = {"Nature": "Natural", "Default": ""}.get(name, name)
    if not name:
        return None
    low = name.lower()

    if vendor == "prusament":
        if re.match(r"^r [A-Z]", name):  # "r Algae Pigment" duplicates the Recycled line
            return None
        if folder == "petg" and ("magnetite" in low or "tungsten" in low):
            return None  # these live in their own folders
        if folder == "petg_magnetite":
            return line, "40% Grey"
        if folder == "petg_tungsten":
            return line, "75% Grey"
        if low.startswith("recycled") and material == "PETG":
            return "Recycled", re.sub(r"(?i)^recycled\s*", "", name) or "Green"
        if line == "Recycled" and material == "PLA":
            return line, {"PLA Recycled": "Natural", "Recycled": "Natural"}.get(name, name.replace(" Pigment", ""))
        if material == "PC":
            if folder == "pc" and low.startswith("blend "):
                line = "Blend"  # "Blend Prusa Green" sits in the plain PC folder
            name = re.sub(r"^Blend\s+", "", name)
            name = {"Carbon Fiber Black": "Black"}.get(name, name)
            if folder == "pc_cf" and low.startswith("blend"):
                name = "Carbon Fiber Black"
            return line, name
    if vendor == "azurefilm":
        if folder == "pla" and "glitter" in low:
            return None  # the Glitter line has these
        if material == "PLA" and low.endswith(" pastel") and folder == "pla":
            return "Pastel", name[: -len(" Pastel")]
        if folder == "tpu_tpe":
            m = re.match(r"^(.*?)\s+(\d+A)$", name)
            if m:
                return f"TPE {m.group(2)}", tidy(m.group(1))
    if vendor == "polymaker":
        if "polylite" in low and len(low) <= 10:  # "PolyLite™" is a line name, not a color
            return None
        if "esd" in low:
            return None  # handled as PETG ESD
        if low == "lw" or (line == "Panchroma" and low == "satin"):
            return None
        name = re.sub(r"^Fiberon\s*-?\s*", "", name)
        if folder == "polylite_pla" and low.startswith("cos version"):
            return None
        name = re.sub(r"^Polymaker Teal$", "Polymaker Teal", name)
    if vendor == "rosa3d_filaments":
        return fix_rosa(material, folder, line, name)
    if vendor in ("elegoo", "buddy3d"):
        name = re.sub(r"(?i)\b(pla|petg)\b\s*", "", name).strip() or name
        name = tidy(name)
    return line, name


ROSA_PETG_PREFIX = [
    (r"^R-PET-G Impact\s+", "Recycled Impact"),
    (r"^R-PET-G\s+", "Recycled"),
    (r"^PET-G HT\s+", "HT"),
    (r"^PET-G Structure\s+", "High Speed Structure"),
    (r"^PET-G Magic\s+", "Magic"),
    (r"^PET-G V0 FR\s+", "V0 FR"),
]


def fix_rosa(material: str, folder: str, line: str, name: str) -> tuple[str, str] | None:
    if material == "PETG":
        if folder == "petg":
            for pattern, new_line in ROSA_PETG_PREFIX:
                if re.match(pattern, name):
                    rest = re.sub(pattern, "", name)
                    rest = re.sub(r"^Army \(Green-Beige-Bronze\)$", "Army", rest)
                    return new_line, tidy(rest)
            return None
        name = re.sub(r"^Pet G\s+", "", name, flags=re.I)
        if folder == "pet_g_hs_high_speed_petg":
            name = re.sub(r"^Galaxy\s+", "", name)
        if folder == "pet_g_galaxy_hs_high_speed_petg":
            name = re.sub(r"^Galaxy\s+", "", name)
        # "Transparent Red" and "Red Transparent" are the same color: use the second form
        m = re.match(r"^Transparent\s+(\S.*)$", name)
        if m:
            name = f"{m.group(1)} Transparent"
        name = re.sub(r"^(?:PET-G|Pet G)\s*\+?\s*", "", name)
        name = re.sub(r"^x-Ray", "X-Ray", name)
        return line, name
    if material == "PLA":
        if folder == "pla":  # one folder, three different lines
            if name.upper().startswith("LW AREO"):
                return "LW Aero", tidy(name[len("LW AREO"):])
            if name.upper().startswith("R-"):
                return "Recycled", tidy(name[2:]).title()
            if name == "Rainbow Pastel":
                return "Pastel", "Rainbow"
            return None
        name = re.sub(r"^Pla\s+", "", name, flags=re.I)
        if name.isupper() and len(name) > 3:
            name = name.capitalize()
        name = re.sub(r"\(([a-z])", lambda m: "(" + m.group(1).upper(), name)
        return line, name
    if material == "TPU":
        m = re.match(r"^(\d+[AD])\s+(.*)$", name)
        if m and line.startswith("@hardness:"):
            return f"{line.split(':', 1)[1]} {m.group(1).upper()}", tidy(m.group(2))
        return line, name
    return line, name


def read_variant(variant_dir: Path):
    """Return (name, hex, weights, tare) or None when there is no usable 1.75 mm data."""
    vfile = variant_dir / "variant.json"
    if not vfile.exists():
        return None
    v = load(vfile)
    hex_ = v.get("color_hex", "")
    if isinstance(hex_, list):  # multi-color: first color as swatch
        hex_ = hex_[0] if hex_ else ""
    if not isinstance(hex_, str) or not HEX_RE.match(hex_):
        return None
    weights, tare = set(), None
    sfile = variant_dir / "sizes.json"
    if sfile.exists():
        for s in load(sfile):
            if s.get("diameter", 1.75) != 1.75:
                continue
            if "filament_weight" in s:
                weights.add(int(s["filament_weight"]))
            if tare is None and s.get("empty_spool_weight"):
                tare = int(s["empty_spool_weight"])
    if not weights:
        return None  # only 2.85 mm or no size data
    return v["name"], hex_.lower(), sorted(w for w in weights if w >= 250) or sorted(weights), tare


def build_vendor(display: str, folder: str, only: set[str] | None, db: Path) -> dict[str, list[dict]]:
    root = db / "data" / folder
    result: dict[str, list[dict]] = {}
    for material_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        material = material_dir.name
        if only and material not in only:
            continue
        mapping = LINES.get((folder, material))
        order: list[str] = []  # lines in dropdown order
        rows: dict[tuple[str, str], dict] = {}

        def add(line, name, hex_, weights, tare=None, mat=material):
            if line not in order_for(mat):
                order_for(mat).append(line)
            key = (mat, line.lower(), name.lower())
            if key not in rows:
                entry = {"name": name, "hex": hex_, "line": line, "weights": weights}
                if tare:
                    entry["tare"] = tare
                rows[key] = entry

        orders: dict[str, list[str]] = {}

        def order_for(mat):
            return orders.setdefault(mat, [])

        if mapping is None:  # material without hand-made map (ASA, PC, ...): derive lines from folder names
            names = {}
            for filament_dir in sorted(p for p in material_dir.iterdir() if p.is_dir()):
                fj = filament_dir / "filament.json"
                names[filament_dir.name] = generic_line(load(fj).get("name", ""), material) if fj.exists() else ""
            mapping = sorted(names.items(), key=lambda kv: (kv[1] != "", kv[1].lower()))
        for dirname, line in mapping:
            if line is None:
                continue
            if dirname.startswith("@"):
                extra = EXTRAS.get((folder, material, dirname))
                if extra and "lines" in extra:
                    for l, weights, colors in extra["lines"]:
                        for cname, chex in colors:
                            add(l, cname, chex, weights)
                elif extra:
                    for cname, chex in extra["colors"]:
                        add(line, cname, chex, extra["weights"], extra.get("tare"))
                continue
            filament_dir = material_dir / dirname
            if not filament_dir.is_dir():
                continue
            for variant_dir in sorted(p for p in filament_dir.iterdir() if p.is_dir()):
                data = read_variant(variant_dir)
                if data is None:
                    continue
                vname, hex_, weights, tare = data
                if material == "PETG" and re.search(r"\bESD\b", vname, re.I):
                    # "Fiberon -ESD Black" -> PETG ESD / line Fiberon / Black
                    cname = re.sub(r"Fiberon|ESD|[-_]", " ", vname, flags=re.I)
                    cname = tidy(re.sub(r"\s+", " ", cname)) or "Black"
                    add("Fiberon", cname, hex_, weights, tare, mat="PETG ESD")
                    continue
                fixed = fix_color(folder, material, dirname, line, vname)
                if fixed is None:
                    continue
                fline, cname = fixed
                if not cname:
                    continue
                add(fline, cname, hex_, weights, tare)
        for mat in orders:
            lines = sorted(orders[mat], key=lambda x: (x != "", x == "Recycled"))  # standard first, Recycled last
            entries = [r for (m, _l, _n), r in rows.items() if m == mat]
            if not entries:
                continue
            entries.sort(key=lambda e: (lines.index(e["line"]), e["name"].lower()))
            result.setdefault(mat, []).extend(entries)
    return result


def initials(name: str) -> str:
    letters = re.sub(r"[^A-Za-z0-9]", "", name)
    return (letters[:2] or "?").upper()


def build_generic(folder: str, skip: set[str], db: Path, brand: str = "") -> dict[str, list[dict]]:
    """Everything the database lists for a brand, without hand-made product lines.

    Product line = the database's filament name without the material word ("Sunlu PLA+" -> "PLA+"),
    "" when nothing is left. Used for all brands that are not curated above, and for the materials of
    curated brands that LINES does not cover.
    """
    root = db / "data" / folder
    result: dict[str, list[dict]] = {}
    for material_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        material = material_dir.name
        if material in skip:
            continue
        rows: dict[tuple[str, str], dict] = {}
        for filament_dir in sorted(p for p in material_dir.iterdir() if p.is_dir()):
            fj = filament_dir / "filament.json"
            fname = load(fj).get("name", "") if fj.exists() else filament_dir.name
            line = generic_line(fname, material)
            if brand and line.lower().startswith(brand.lower()):  # "Artillery Basic" under Artillery -> "Basic"
                line = tidy(line[len(brand):])
            for variant_dir in sorted(p for p in filament_dir.iterdir() if p.is_dir()):
                data = read_variant(variant_dir)
                if data is None:
                    continue
                vname, hex_, weights, tare = data
                vline = line
                split = re.match(r"^(.*?)\s*\(([^)]*)$", line)
                if split and ")" in vname and "(" not in vname:  # the database cut "Name (a, b)" at the comma
                    vline = tidy(split.group(1))
                    vname = f"{split.group(2)}, {vname.split(')')[0]}"
                cname = clean_color(vname, material)
                if len(cname) < 2:
                    continue
                key = (vline.lower(), cname.lower())
                if key in rows:
                    continue
                entry = {"name": cname, "hex": hex_, "line": vline, "weights": weights}
                if tare:
                    entry["tare"] = tare
                rows[key] = entry
        if rows:
            result[material] = sorted(rows.values(), key=lambda e: (e["line"] != "", e["line"].lower(), e["name"].lower()))
    return result


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9+]", "", text.lower())


def _spelling_score(text: str) -> tuple[int, int]:
    shouting = any(len(w) > 3 and w.isupper() for w in text.split())
    return (0 if shouting else 1, sum(c.isupper() for c in text))


def canonicalize(rows_by_material: dict[str, list[dict]]) -> None:
    """One spelling per product line ("Primaselect" / "PrimaSelect" / "PRIMASELECT" -> "PrimaSelect") and no
    duplicate (line, color) pairs, comparing without case, spaces and punctuation. Order is kept."""
    # one spelling per word across the whole brand ("Primaselect" -> "PrimaSelect" when both occur)
    words: dict[str, str] = {}
    for rows in rows_by_material.values():
        for r in rows:
            for w in r["line"].split():
                k = norm(w)
                if len(k) >= 4 and (k not in words or _spelling_score(w) > _spelling_score(words[k])):
                    words[k] = w
    for rows in rows_by_material.values():
        for r in rows:
            r["line"] = " ".join(words.get(norm(w), w) if len(norm(w)) >= 4 else w for w in r["line"].split())
    for rows in rows_by_material.values():
        best: dict[str, str] = {}
        for r in rows:
            k = norm(r["line"])
            if k not in best or _spelling_score(r["line"]) > _spelling_score(best[k]):
                best[k] = r["line"]
        seen: set[tuple[str, str]] = set()
        kept = []
        for r in rows:
            key = (norm(r["line"]), norm(r["name"]))
            if key in seen:
                continue
            seen.add(key)
            kept.append({**r, "line": best[norm(r["line"])]})
        # keep each line together, in order of first appearance, the plain product first
        order = list(dict.fromkeys(r["line"] for r in kept))
        kept.sort(key=lambda e: (e["line"] != "", order.index(e["line"])))
        rows[:] = kept


def fold_children(catalog: dict, folders: dict[str, str], children: list[tuple[str, str]], db: Path) -> None:
    """Brands the database marks with `parent_brand` are product families of that brand, not brands of their own.

    "PolyFlex" (parent: polymaker) becomes the product line "PolyFlex" under Polymaker. A color that the parent
    already lists under the same line (compared without spaces and punctuation) is not added twice.
    """
    for child_folder, parent_folder in children:
        parent = {"name": folders[parent_folder]} if parent_folder in folders else None
        if parent is None:
            print(f"note: {child_folder} has parent {parent_folder}, which is not in the catalog; skipped")
            continue
        child = load(db / "data" / child_folder / "brand.json")
        cname = tidy(child.get("name") or child_folder)
        mats = catalog[parent["name"]]
        for mat, rows in build_generic(child_folder, set(), db, cname).items():
            target = mats.setdefault(mat, [])
            seen = {(norm(r["line"]), norm(r["name"])) for r in target}
            for r in rows:
                r = {**r, "line": re.sub(r"\bTPU(\d{2})\b", r"\1A", r["line"])}
                line = cname if not r["line"] else (r["line"] if norm(r["line"]).startswith(norm(cname)) else f"{cname} {r['line']}")
                if (norm(line), norm(r["name"])) in seen:
                    continue
                seen.add((norm(line), norm(r["name"])))
                target.append({**r, "line": line})
            order = list(dict.fromkeys(r["line"] for r in target))
            target.sort(key=lambda e: (e["line"] != "", order.index(e["line"])))


def build(db: Path, out: Path) -> None:
    www = out / "www"
    (www / "logos").mkdir(parents=True, exist_ok=True)

    vendors, catalog = [], {}
    curated_folders: set[str] = set()
    folders: dict[str, str] = {}  # database folder -> display name
    for display, folder, code, only in VENDORS:
        website = WEBSITES.get(display)
        if folder:
            website = load(db / "data" / folder / "brand.json").get("website")
        vendors.append({"name": display, "code": code, "logo": LOGO_NAMES[display], "website": website})
        if folder is None:
            catalog[display] = {
                mat: [{"name": n, "hex": h, "line": "", "weights": [1000]} for n, h in colors]
                for mat, colors in RAISE3D.items()
            }
        else:
            catalog[display] = build_vendor(display, folder, only, db)
            curated_folders.add(folder)
            folders[folder] = display
            # materials the hand-made lines do not cover come straight from the database
            for mat, rows in build_generic(folder, set(catalog[display]) | {m for m in USED}, db).items():
                catalog[display].setdefault(mat, rows)

    names = {v["name"].lower() for v in vendors}
    children: list[tuple[str, str]] = []
    for brand_dir in sorted(p for p in (db / "data").iterdir() if p.is_dir() and p.name not in curated_folders):
        bfile = brand_dir / "brand.json"
        if not bfile.exists():
            continue
        brand = load(bfile)
        display = tidy(brand.get("name") or brand_dir.name)
        if brand.get("parent_brand"):  # a product family of another brand: folded in below
            children.append((brand_dir.name, brand["parent_brand"]))
            continue
        if display.lower() in names:
            continue
        rows = build_generic(brand_dir.name, set(), db, display)
        if not rows:
            continue
        names.add(display.lower())
        folders[brand_dir.name] = display
        vendors.append({"name": display, "code": initials(display), "logo": None, "website": brand.get("website")})
        catalog[display] = rows
    fold_children(catalog, folders, children, db)
    for name, mats in catalog.items():
        if name == "Polymaker" or name not in HAND_MADE:  # the other hand-made brands are already tidy
            canonicalize(mats)
    # curated brands first (in the order above), the rest alphabetical
    rest = sorted(vendors[len(VENDORS):], key=lambda v: v["name"].lower())
    vendors = vendors[: len(VENDORS)] + rest
    all_materials = sorted({m for v in catalog.values() for m in v}, key=lambda m: (MATERIALS.index(m) if m in MATERIALS else 99, m))

    data = {
        "source": "Open Filament Database (MIT), https://github.com/OpenFilamentCollective/open-filament-database (snapshot 2026-11-01); "
                  "some entries (Raise3D, PolyTerra, PolyFlex, AzureFilm Pearl) added by hand",
        "vendors": vendors,
        "materials": all_materials,
        "standard_colors": [{"name": n, "hex": h} for n, h in STANDARD_COLORS],
        "catalog": catalog,
    }
    (www / "catalog.json").write_text(
        json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8"
    )
    total = sum(len(e) for m in catalog.values() for e in m.values())
    print(f"{len(vendors)} vendors, {total} colors, {(www / 'catalog.json').stat().st_size // 1024} KB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(Path(sys.argv[1]), Path(__file__).resolve().parent.parent / "custom_components" / "spool_inventory")

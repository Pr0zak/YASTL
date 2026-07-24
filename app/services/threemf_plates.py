"""Bambu Studio / OrcaSlicer multi-plate 3MF detection.

A .3mf is an OPC zip. trimesh reads only ``3D/3dmodel.model`` and ignores the
``Metadata/`` folder, so plate structure must be parsed from the zip directly.
Bambu/Orca store it in ``Metadata/model_settings.config`` (XML). Detection +
plate enumeration is a cheap zip peek — no mesh load. Per-plate previews are
already embedded (``Metadata/plate_N.png``), so we reuse them.

Validated against the Bambu source constants + independent teardowns; should be
double-checked against a real multi-plate export before relying on edge cases.
"""

import logging
import re
import xml.etree.ElementTree as ET
import zipfile

logger = logging.getLogger("yastl")

MODEL_SETTINGS = "Metadata/model_settings.config"
_PLATE_PNG_RE = re.compile(r"^Metadata/plate_(\d+)\.png$")


def _kv(el) -> dict:
    """Collect <metadata key= value=/> children into a dict."""
    return {m.get("key"): m.get("value") for m in el.findall("metadata")}


def _parse_plates(zf: zipfile.ZipFile) -> list[dict]:
    root = ET.fromstring(zf.read(MODEL_SETTINGS))
    plates = []
    for p in root.findall("plate"):
        meta = _kv(p)
        instances = [_kv(mi) for mi in p.findall("model_instance")]
        object_ids = []
        for inst in instances:
            oid = inst.get("object_id")
            if oid and oid.isdigit():
                object_ids.append(int(oid))
        try:
            plater_id = int(meta.get("plater_id") or 0)
        except (TypeError, ValueError):
            plater_id = 0
        plates.append({
            "plater_id": plater_id,
            "name": meta.get("plater_name", ""),          # NOTE: Bambu typo, really "plater_name"
            "object_ids": object_ids,
            "instance_count": len(instances),
            "thumbnail": meta.get("thumbnail_file"),        # e.g. Metadata/plate_1.png
        })
    return sorted(plates, key=lambda p: p["plater_id"])


def inspect_3mf(path: str) -> dict:
    """Return {kind, plate_count, plates}. kind is 'bambu_project' or 'plain_3mf'.

    plate_count > 1 means multi-plate. Never raises — a malformed/plain 3MF
    returns a single-plate plain result.
    """
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            has_settings = MODEL_SETTINGS in names
            has_plate_png = any(_PLATE_PNG_RE.match(n) for n in names)
            if not has_settings and not has_plate_png:
                return {"kind": "plain_3mf", "plate_count": 1, "plates": []}

            plates = _parse_plates(z) if has_settings else []
            if not plates:
                # Sliced-only edge case: derive plates from plate_N.png.
                idx = sorted({int(m.group(1)) for n in names
                              if (m := _PLATE_PNG_RE.match(n))})
                plates = [{"plater_id": i, "name": "", "object_ids": [],
                           "instance_count": 0, "thumbnail": f"Metadata/plate_{i}.png"}
                          for i in idx]
            return {
                "kind": "bambu_project" if (has_settings or has_plate_png) else "plain_3mf",
                "plate_count": max(1, len(plates)),
                "plates": plates,
            }
    except (zipfile.BadZipFile, ET.ParseError, KeyError, OSError) as e:
        logger.debug("inspect_3mf failed for %s: %s", path, e)
        return {"kind": "plain_3mf", "plate_count": 1, "plates": []}


def read_plate_thumbnail(path: str, plate: dict) -> tuple[bytes | None, str | None]:
    """Return (png_bytes, 'image/png') for a plate, reusing Bambu's embedded
    preview. Resolves the path from the plate's thumbnail_file metadata, with a
    plate_{plater_id}.png fallback. Returns (None, None) if not present."""
    candidates = []
    if plate.get("thumbnail"):
        candidates.append(plate["thumbnail"])
    candidates.append(f"Metadata/plate_{plate.get('plater_id', 1)}.png")
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            for name in candidates:
                if name in names:
                    return z.read(name), "image/png"
    except (zipfile.BadZipFile, KeyError, OSError):
        pass
    return None, None

"""Write a site for the web: small binaries the browser reads with fetch + typed arrays.

data/<site>/
  meta.json   dates, grid, layer offsets and scales, peer block layout, provenance
  grid.bin    one value per pixel per layer (z, style, since, cover, + damage / up / east)
  peers.bin   peer median and spread per WorldCover class, per 1 km block, per date
  series/<ty>_<tx>.bin   per-pixel HH, HV (and displacement) series in 32 x 32 tiles, read on click

Quantisation (decode in js/data.js):
  dB    uint8   v = q / 4 - 40          (255 = no data)   0.25 dB steps over -40..+23.5
  sd    uint8   v = q / 20              (255 = no data)
  z     int8    v = q / 10              (-128 = no data)
  cm    int16   v = q / 10              (-32768 = no data) displacement, rates in cm or cm/yr
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

from .config import Site
from .grid import Grid

ROOT = Path(__file__).resolve().parent.parent / "data"
TILE = 32


def q_db(a):  return np.where(np.isnan(a), 255, np.clip(np.round((a + 40) * 4), 0, 254)).astype(np.uint8)
def q_sd(a):  return np.where(np.isnan(a), 255, np.clip(np.round(a * 20), 0, 254)).astype(np.uint8)
def q_z(a):   return np.where(np.isnan(a), -128, np.clip(np.round(a * 10), -127, 127)).astype(np.int8)
def q_cm(a):  return np.where(np.isnan(a), -32768, np.clip(np.round(a * 10), -32767, 32767)).astype(np.int16)


class _Blob:
    """Concatenates arrays, keeping every one 4-byte aligned so JS typed arrays can view it."""
    def __init__(self):
        self.parts, self.size, self.index = [], 0, {}

    def add(self, name, arr, kind):
        pad = (-self.size) % 4
        if pad:
            self.parts.append(b"\0" * pad); self.size += pad
        b = np.ascontiguousarray(arr).tobytes()
        self.index[name] = {"offset": self.size, "dtype": str(arr.dtype), "kind": kind, "shape": list(arr.shape)}
        self.parts.append(b); self.size += len(b)

    def write(self, path):
        path.write_bytes(b"".join(self.parts))


def write(site: Site, grid: Grid, cover: np.ndarray, res: dict, source: str) -> Path:
    if 'synthetic' in source.lower() or 'mock' in source.lower():
        raise ValueError('Only measured source data may be exported')
    out = ROOT / site.id
    keep = {p.name: p.read_bytes() for p in out.glob("*") if p.is_file() and p.suffix in (".json", ".geojson")
            and p.name != "meta.json"}                       # context files (fires, alerts) stay
    if out.exists():
        shutil.rmtree(out)
    (out / "series").mkdir(parents=True)
    for name, b in keep.items():
        (out / name).write_bytes(b)

    H, W = grid.shape
    T = len(res["dates"])

    g = _Blob()
    g.add("z", q_z(res["z"]), "z")
    g.add("style", res["style"].astype(np.uint8), "code")
    g.add("since", np.where(res["since"] < 0, 255, res["since"]).astype(np.uint8), "index")
    g.add("cover", cover.astype(np.uint8), "code")
    if "damage" in res:
        g.add("damage", q_z(res["damage"]), "z")
    if "coseismic" in res:
        g.add("coseismic", q_cm(res["coseismic"]), "cm")
    if "up" in res:
        g.add("up", q_cm(res["up"]), "cm")
        g.add("east", q_cm(res["east"]), "cm")
    g.write(out / "grid.bin")

    p = _Blob()
    bsize = res["hh_blocks"]["size"]
    classes = sorted(res["hh_blocks"]["classes"])
    for c in classes:
        hm, hs = res["hh_blocks"]["classes"][c]
        vm, vs = res["hv_blocks"]["classes"][c]
        p.add(f"{c}.hh_med", q_db(hm), "db"); p.add(f"{c}.hh_sd", q_sd(hs), "sd")
        p.add(f"{c}.hv_med", q_db(vm), "db"); p.add(f"{c}.hv_sd", q_sd(vs), "sd")
        if "disp_blocks" in res and c in res["disp_blocks"]["classes"]:
            dm, ds = res["disp_blocks"]["classes"][c]
            p.add(f"{c}.disp_med", q_cm(dm), "cm"); p.add(f"{c}.disp_sd", q_cm(ds), "cm")
    p.write(out / "peers.bin")
    bh, bw = res["hh_blocks"]["classes"][classes[0]][0].shape[1:]

    has_disp = "disp" in res
    tiles = []
    for ty in range(0, H, TILE):
        for tx in range(0, W, TILE):
            def cut(a, fill):
                t = np.full((a.shape[0], TILE, TILE), fill, a.dtype)
                s = a[:, ty:ty + TILE, tx:tx + TILE]
                t[:, :s.shape[1], :s.shape[2]] = s
                return t
            s = _Blob()
            s.add("hh", cut(q_db(res["hh"]), 255), "db")
            s.add("hv", cut(q_db(res["hv"]), 255), "db")
            if has_disp:
                s.add("disp", cut(q_cm(res["disp"]), -32768), "cm")
            s.write(out / "series" / f"{ty // TILE}_{tx // TILE}.bin")
            tiles.append(s.index)

    w, so, e, n = grid.lonlat_bounds()
    meta = {
        "id": site.id, "name": site.name, "source": source,
        "dates": res["dates"], "event": site.event,
        "bounds": [w, so, e, n], "width": W, "height": H, "pixel_m": site.pixel_m,
        "grid": g.index,
        "peers": {"block": bsize, "bw": int(bw), "bh": int(bh), "classes": classes, "layers": p.index},
        "series": {"tile": TILE, "layers": tiles[0] if tiles else {}},
        "damage_pair": list(res.get("damage_pair", [])) or None,
        "styles": {"1": "drop", "2": "flood", "3": "drift", "4": "step"},
        # context files that sit next to the site (fires, alerts, validation), so the web asks only for those
        "context": {k: f for k, f in (("fires", "fires.json"), ("alerts", "alerts.geojson"),
                                      ("validation", "validation.json")) if (out / f).exists()},
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    return out

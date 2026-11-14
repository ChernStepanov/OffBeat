"""Prepare real, reproducible DEM context for the three NISAR study areas.

Uses only the Python standard library. Sources: Mapzen Terrain Tiles on AWS;
Terrarium decoding follows https://github.com/tilezen/joerd/blob/master/docs/formats.md.
This changes neither the NISAR measurements nor their sampling density.
"""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import math
import struct
import urllib.request
import zlib

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'data/terrain-cache'
OUTPUT = ROOT / 'data/terrain'
ZOOM, SIZE, GRID = 13, 256, 257


def png_rgb(raw):
    if raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Source is not a PNG')
    offset, compressed = 8, bytearray()
    while offset < len(raw):
        length = struct.unpack_from('>I', raw, offset)[0]
        kind = raw[offset + 4:offset + 8]
        data = raw[offset + 8:offset + 8 + length]
        crc = struct.unpack_from('>I', raw, offset + 8 + length)[0]
        if zlib.crc32(kind + data) & 0xffffffff != crc:
            raise ValueError('PNG checksum mismatch')
        if kind == b'IHDR':
            width, height, bits, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
            if bits != 8 or color not in (2, 6) or interlace:
                raise ValueError('Expected non-interlaced RGB/RGBA 8-bit PNG')
            channels = 3 if color == 2 else 4
        if kind == b'IDAT':
            compressed.extend(data)
        offset += length + 12
        if kind == b'IEND':
            break
    decompressed = zlib.decompress(compressed)
    stride = width * channels
    if len(decompressed) != height * (stride + 1):
        raise ValueError('Unexpected PNG data length')
    previous, result = bytearray(stride), []
    for y in range(height):
        row_start = y * (stride + 1)
        mode = decompressed[row_start]
        row = bytearray(decompressed[row_start + 1:row_start + stride + 1])
        for i in range(stride):
            a = row[i - channels] if i >= channels else 0
            b = previous[i]
            c = previous[i - channels] if i >= channels else 0
            if mode == 1:
                predictor = a
            elif mode == 2:
                predictor = b
            elif mode == 3:
                predictor = (a + b) // 2
            elif mode == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                predictor = a if pa <= pb and pa <= pc else b if pb <= pc else c
            elif mode == 0:
                predictor = 0
            else:
                raise ValueError('Unknown PNG filter')
            row[i] = (row[i] + predictor) & 255
        result.append([row[i] * 256 + row[i + 1] + row[i + 2] / 256 - 32768 for i in range(0, stride, channels)])
        previous = row
    return result


def mercator_pixel(lon, lat):
    total = 2 ** ZOOM * SIZE
    return ((lon + 180) / 360 * total,
            (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * total)


def prepare(name):
    site = json.loads((ROOT / f'data/{name}.json').read_text())
    original = site['grid']['bbox']
    cx, cy = (original['w'] + original['e']) / 2, (original['s'] + original['n']) / 2
    # 3 x the study area's width provides real geographic context around the SAR sample.
    half_x, half_y = (original['e'] - original['w']) * 1.5, (original['n'] - original['s']) * 1.5
    bounds = dict(w=cx - half_x, e=cx + half_x, s=cy - half_y, n=cy + half_y)
    west, north = mercator_pixel(bounds['w'], bounds['n'])
    east, south = mercator_pixel(bounds['e'], bounds['s'])
    tiles, sources = {}, []
    for tx in range(math.floor((west - 1) / SIZE), math.floor((east + 1) / SIZE) + 1):
        for ty in range(math.floor((north - 1) / SIZE), math.floor((south + 1) / SIZE) + 1):
            url = f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{ZOOM}/{tx}/{ty}.png'
            path = CACHE / f'{ZOOM}_{tx}_{ty}.png'
            if not path.exists():
                with urllib.request.urlopen(url, timeout=60) as response:
                    raw = response.read()
                png_rgb(raw)  # validate before caching
                path.write_bytes(raw)
            raw = path.read_bytes()
            tiles[tx, ty] = png_rgb(raw)
            sources.append(dict(url=url, sha256=sha256(raw).hexdigest(), bytes=len(raw)))
            print(name, tx, ty, flush=True)

    def native(x, y):
        return tiles[x // SIZE, y // SIZE][y % SIZE][x % SIZE]

    def elevation(lon, lat):
        # PNG values are at pixel centres, not at pixel edges.
        x, y = mercator_pixel(lon, lat)
        x, y = x - .5, y - .5
        ix, iy = math.floor(x), math.floor(y)
        fx, fy = x - ix, y - iy
        return ((1 - fy) * ((1 - fx) * native(ix, iy) + fx * native(ix + 1, iy))
                + fy * ((1 - fx) * native(ix, iy + 1) + fx * native(ix + 1, iy + 1)))

    values = [round(elevation(bounds['w'] + (bounds['e'] - bounds['w']) * x / (GRID - 1),
                              bounds['n'] - (bounds['n'] - bounds['s']) * y / (GRID - 1)), 2)
              for y in range(GRID) for x in range(GRID)]
    numeric = json.dumps(values, separators=(',', ':'), allow_nan=False).encode()
    result = dict(schema_version=1, site=name, source='Mapzen Terrain Tiles / AWS Open Data',
                  kind='measured_dem_context', n=GRID, bbox=bounds, study_bbox=original,
                  height_m=values, min_m=min(values), max_m=max(values),
                  provenance=dict(retrieved_utc=datetime.now(timezone.utc).isoformat(), sources=sources,
                                  format='Terrarium RGB: R*256+G+B/256-32768 metres', zoom=ZOOM,
                                  sampling='Bilinear source-pixel-centre interpolation in Web Mercator; uniform WGS84 output nodes, row-major north to south',
                                  height_sha256=sha256(numeric).hexdigest(),
                                  attribution='Mapzen Terrain Tiles; USGS SRTM/GMTED2010; Mexico: INEGI, Continental relief, 2016',
                                  attribution_url='https://github.com/tilezen/joerd/blob/master/docs/attribution.md',
                                  limitations=['Historical DEM, not a current NISAR height measurement',
                                               'Source resolution and vertical datum vary with upstream tiles',
                                               'Output mesh spacing is not independently measured ground resolution',
                                               'NISAR sample positions/values are unchanged; no new SAR observations are generated']))
    (OUTPUT / f'{name}.json').write_text(json.dumps(result, separators=(',', ':'), allow_nan=False) + '\n')
    print(name, len(values), min(values), max(values), flush=True)


if __name__ == '__main__':
    CACHE.mkdir(exist_ok=True)
    OUTPUT.mkdir(exist_ok=True)
    for site_name in ['amazon', 'mexico', 'venezuela']:
        prepare(site_name)

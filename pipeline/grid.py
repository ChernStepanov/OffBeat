"""One output grid per site: EPSG:4326, north-up, pixels ~site.pixel_m metres on the ground
(lon step widened by 1/cos(lat) so pixels are square on the ground).

Every layer (GCOV, GUNW, WorldCover, alerts) is resampled onto this grid, so the
analysis works on plain aligned numpy arrays and the web gets one raster shape.
"""
from dataclasses import dataclass
import math

from pyproj import CRS, Transformer
from rasterio.transform import Affine, from_origin

from .config import Site


@dataclass(frozen=True)
class Grid:
    crs: CRS
    transform: Affine
    width: int
    height: int

    @property
    def shape(self) -> tuple[int, int]:
        return self.height, self.width

    def lonlat_bounds(self) -> tuple[float, float, float, float]:
        """west, south, east, north of the grid's outer edge in EPSG:4326."""
        to_ll = Transformer.from_crs(self.crs, 4326, always_xy=True)
        x0, y0 = self.transform * (0, 0)
        x1, y1 = self.transform * (self.width, self.height)
        xs, ys = to_ll.transform([x0, x1, x0, x1], [y0, y0, y1, y1])
        return min(xs), min(ys), max(xs), max(ys)


def utm_crs(lon: float, lat: float) -> CRS:
    zone = int(math.floor((lon + 180) / 6) + 1)
    return CRS.from_epsg((32600 if lat >= 0 else 32700) + zone)


def site_grid(site: Site) -> Grid:
    """Lat/lon grid so the web map can lay the raster over the bbox with no warping."""
    w, s, e, n = site.bbox
    dlat = site.pixel_m / 111320.0
    dlon = dlat / math.cos(math.radians((s + n) / 2))
    width, height = math.ceil((e - w) / dlon), math.ceil((n - s) / dlat)
    return Grid(CRS.from_epsg(4326), from_origin(w, n, dlon, dlat), width, height)

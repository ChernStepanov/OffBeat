"""Demo sites: AOIs, NISAR tracks and dates checked in the ASF/CMR catalogue (2026-11-14)."""
from dataclasses import dataclass, field

# NISAR L2 collections in CMR (provider ASF). PROVISIONAL holds the long series; VALIDATED starts 2026-10-21.
GCOV = ["NISAR_L2_GCOV_BETA_V1", "NISAR_L2_GCOV_PROVISIONAL_V1", "NISAR_L2_GCOV_V1"]
GUNW = ["NISAR_L2_GUNW_BETA_V1", "NISAR_L2_GUNW_PROVISIONAL_V1", "NISAR_L2_GUNW_V1"]

# No acquisitions anywhere in this window.
GLOBAL_GAP = ("2026-07-27", "2026-08-10")


@dataclass(frozen=True)
class Track:
    track: int
    direction: str          # "A" ascending, "D" descending
    frames: tuple[int, ...]


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    bbox: tuple[float, float, float, float]   # west, south, east, north (EPSG:4326)
    start: str
    end: str
    tracks: tuple[Track, ...]
    pixel_m: int = 100                        # output grid; GCOV is 20 m, we aggregate for the web
    event: str | None = None                  # ISO date of a known event
    gaps: tuple[tuple[str, str], ...] = field(default_factory=tuple)


SITES = {
    "mexico": Site(
        id="mexico", name="Mexico City",
        bbox=(-99.25, 19.25, -98.90, 19.60),
        start="2025-10-25", end="2026-11-06",
        # two geometries -> vertical and east-west motion
        tracks=(Track(19, "A", (11,)), Track(113, "D", (79,))),
    ),
    "amazon": Site(
        id="amazon", name="Itupiranga, Para",
        bbox=(-49.50, -5.00, -49.05, -4.55),
        start="2025-11-01", end="2026-11-03",
        tracks=(Track(45, "A", (175,)), Track(146, "A", (175,))),
        # BETA (uncalibrated) ends 2026-01-19, PROVISIONAL starts 2026-06-17
        gaps=(("2026-01-20", "2026-06-16"),),
    ),
    "venezuela": Site(
        id="venezuela", name="Caracas and Catia La Mar",
        bbox=(-67.25, 10.38, -66.78, 10.66),   # epicentre of the M7.5 at -67.22 and Caracas + La Guaira
        start="2025-11-01", end="2026-11-04",
        # 162A/007 has the pair 2026-06-13 -> 2026-06-25, about 12 h after the M7.5
        tracks=(Track(162, "A", (7,)), Track(126, "D", (83,)), Track(61, "A", (7,))),   # first ascending + descending pair is decomposed
        event="2026-06-24",
    ),
}

# OffBeat

NISAR change finder for NASA Space Apps 2026, challenge “Dancing with the SARs”.

Rice paddies, swamps and forests each have their own backscatter rhythm. OffBeat compares every
NISAR pixel with nearby pixels of the same ESA WorldCover class, flags the ones that fall out of
step (z-score against peers), names the shape of the change and lets you hear it.

| Style | Signal | Usual cause |
|---|---|---|
| HV drop | sharp fall in HV | clearing, fire |
| HH jump | HH rises by double bounce | flooded vegetation |
| Slow drift | phase drifts over months (GUNW) | subsidence |
| Step | displacement jumps on one date | earthquake |

## Run

No build step. Any static server:

```bash
python3 -m http.server 8765
```

Then open http://localhost:8765/#mexico (also `#amazon`, `#venezuela`).

## Layout

- `index.html`, `css/offbeat.css` — the page, desktop-2005 look on purpose.
- `js/mock.js` — synthetic pixels over the real demo AOIs and acquisition dates. Replace with pipeline output.
- `js/chart.js` — HH/HV and displacement plots against the peer band.
- `js/sonify.js` — WebAudio: peers keep the beat, the pixel plays its curve, slips late and sour when it strays.
- `js/app.js` — maps (Leaflet), pixel card, top list, player.

## Pipeline

Python, in `pipeline/`. Set up once:

```bash
python3 -m venv .venv && .venv/bin/pip install numpy scipy h5py rasterio pyproj earthaccess asf_search requests pillow pytest
```

Run a site (writes `data/<site>/`, which the page reads; without it the page falls back to `js/mock.js`):

```bash
.venv/bin/python -m pipeline.run mexico              # real NISAR, needs an Earthdata login in ~/.netrc
.venv/bin/python -m pipeline.run mexico --synthetic  # invented radar on the real grid and real WorldCover
```

| Step | Module | What it does |
|---|---|---|
| search, read | `nisar.py` | CMR search by AOI and track; reads only the AOI window of each remote HDF5 (GCOV backscatter, GUNW phase, coherence, LOS vectors) |
| land cover | `cover.py` | ESA WorldCover 2021 straight from the public COGs on AWS |
| peers | `peers.py` | per class and date: median and 1.4826 x MAD in 1 km blocks, averaged over 3 km |
| styles | `classify.py` | one change point per pixel; HV drop, HH jump, displacement step or steady drift |
| InSAR | `insar.py` | chains GUNW pairs into displacement; ascending + descending -> vertical and east; coherence loss in built-up areas -> damage proxy |
| context | `context_amazon.py` | NASA FIRMS fires and INPE DETER alerts; checks OffBeat's clearings against them |
| export | `export.py` | `meta.json`, `grid.bin`, `peers.bin`, per-pixel series in 32 x 32 tiles |

Tests: `.venv/bin/python -m pytest pipeline/tests -q -m "not network"`.

## Data

NASA-ISRO NISAR (L2 GCOV, L2 GUNW) via ASF DAAC, ESA WorldCover 10 m, Sentinel-2 cloudless by EOX
for the optical check (to be replaced by date-matched Sentinel-2 / HLS).

## Font

W95FA by Alina Sava, a pixel re-creation of MS Sans Serif, SIL Open Font License 1.1 (`fonts/W95FA-OFL.txt`).
It sits on its pixel grid at 12.5px (80 font units = 1px), so the UI uses that size. The font has no `— – · ≥ ² … ▶`,
so the UI writes `-`, `>=`, `...` and `sq km` instead.

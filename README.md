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

## Real data status

The default application uses real NISAR subsets for Mexico: measured HH/HV on
2025-10-30 and 2025-11-11 plus an exploratory relative GUNW LOS pair. The prepared
case works without login. Earthdata authorization is needed only to re-extract
source data. Missing and quality-rejected measurements remain unavailable.
See [download, processing and provenance instructions](docs/real-nisar.md).

## Run

No build step. Any static server:

```bash
python3 -m http.server 8765
```

Then open http://localhost:8765/#mexico (also `#amazon`, `#venezuela`).

## Layout

- `index.html`, `css/offbeat.css` — the page, desktop-2005 look on purpose.
- `js/data.js` — loads `data/mexico.json`; never falls back to synthetic values.
- `js/mock.js` — legacy synthetic generator, no longer loaded by the application.
- `scripts/subset_nisar.py` — local authenticated extraction, GUNW quality filtering and provenance.
- `js/chart.js` — HH/HV and displacement plots against the peer band.
- `js/sonify.js` — WebAudio: peers keep the beat, the pixel plays its curve, slips late and sour when it strays.
- `js/app.js` — maps (Leaflet), pixel card, top list, player.

## Data

NASA-ISRO NISAR (L2 GCOV, L2 GUNW) via ASF DAAC, ESA WorldCover 10 m, Sentinel-2 cloudless by EOX
for the optical check (to be replaced by date-matched Sentinel-2 / HLS).

## Font

W95FA by Alina Sava, a pixel re-creation of MS Sans Serif, SIL Open Font License 1.1 (`fonts/W95FA-OFL.txt`).
It sits on its pixel grid at 12.5px (80 font units = 1px), so the UI uses that size. The font has no `— – · ≥ ² … ▶`,
so the UI writes `-`, `>=`, `...` and `sq km` instead.

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
- `js/mock.js` — synthetic sites in the shape of [docs/data-contract.md](docs/data-contract.md). Replace with real files.
- `js/chart.js` — HH/HV and displacement plots against the peer band.
- `js/sonify.js` — WebAudio: peers keep the beat, the pixel plays its curve, slips late and sour when it strays.
- `js/app.js` — maps (Leaflet), pixel card, top list, player.
- `docs/coverage.md` — NISAR coverage and dates for the demo sites.

## Data

NASA-ISRO NISAR (L2 GCOV, L2 GUNW) via ASF DAAC, ESA WorldCover 10 m, Sentinel-2 cloudless by EOX
for the optical check (to be replaced by date-matched Sentinel-2 / HLS).

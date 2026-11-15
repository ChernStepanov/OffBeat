# Preliminary Amazon candidate screen — 15 November 2026

This is a post-hoc screen of five existing OffBeat candidates, **not** an independent test or a claim that NASA or another system missed an event. The ranking and location were already known before this review. Source identifiers, SHA-256 receipts, notes and limitations are in [`amazon-candidate-visual-check-2026-11-15.json`](../data/analysis/amazon-candidate-visual-check-2026-11-15.json).

Reproduce the visual contact sheet with `python scripts/amazon_candidate_contact_sheet.py`. This loads the existing 256 × 256 prepared optical previews, crops 64 × 64 pixels around each candidate, enlarges by nearest-neighbour sampling, and marks approximate positions. The output is a review aid, not a measurement or an independently acquired image.

The NISAR GCOV pair is 23 August and 4 September 2026. The earlier comparison used Sentinel-2 images of 14 August and **3 September**: both were before the second radar date. The revised, content-addressed candidate report uses 14 August and 21 September, so the optical images bracket both radar acquisitions; they do not date the change to that radar interval. The latter view is 17 days after the second radar acquisition and has masked/cloudy areas. The third date, 3 September, remains part of this visual audit.

- **r74-c99:** the strongest potentially interpretable optical cue is a field-like patch that looks greener on 14 August and browner in both September previews. Its single-cell HV change is −5.92 dB; the candidate score −3.74 is based on a smoothed, locally corrected surface, not that one-cell value. Crop conditions, moisture, illumination and processing remain possible explanations. This is **not established deforestation or fire**.
- **r52-c44:** modest visual colour differences in a field-like area; no verified event or cause.
- **r23-c67:** a pale, cleared-looking patch is already present on 14 August. Its origin and date are unknown, so it cannot be claimed as a new clearing inside the radar interval. Its single-cell HV change is −1.04 dB even though the smoothed candidate score is −3.49; those values describe different quantities.
- **r109-c103:** vegetation looks broadly similar at this preview resolution; radar changes and smaller optical changes are not ruled out.
- **r3-c30:** near the image edge, with incomplete context and nearby clouds. A wider clear image is necessary.

The project's coarse ERA5 reanalysis estimates 0.5 mm and 0.4 mm of precipitation in the seven complete days before the two radar dates. Its approximately 0.25° grid is not a pixel-scale observation and cannot establish soil moisture or remove weather effects.

## HH, HV and local context

Reproduce `data/analysis/amazon-dense-polarizations-2026-11-15.json` with
`python scripts/audit_amazon_polarizations.py`. For each already-selected marker
the script calculates both channels on valid positive native-grid values at both
dates. It reports the selected cell, the 3×3 median including that cell, and the
median of a surrounding 31×31 window excluding the 3×3. Context may contain
different land covers and is clipped where it meets the available grid. These
neighbours are not independent observations or labels.

For `r74-c99`, the selected cell has HH −1.79 dB and HV −5.92 dB; 3×3 medians
are −1.41 and −4.14 dB, respectively. Both polarizations and nearby cells
decrease, but this does not establish a cause. For `r109-c103`, the selected
cell rises in HH and HV (+1.35 and +3.17 dB), while the 3×3 HH median is
−0.78 dB and the HV median is +2.49 dB. This disagreement is relevant context,
not a classified event. Full valid counts, quantiles, clipped-window flags,
input granules and hashes are retained in the report.

The existing [external audit](amazon-external-audit-v2.md) did not find a point-cover match among the local alert geometries for its own selected points; its dataset and selection are not a complete global archive and are not the same as a full independent search for these five native-grid markers. A missing match would not prove novelty.

NASA already describes [combining L-band SAR and Landsat for forest-loss alerts](https://science.nasa.gov/earth/earth-observatory/faster-detection-of-forest-loss/), and NASA/JPL lists [OPERA surface-disturbance products](https://www.jpl.nasa.gov/go/opera/products/). OffBeat's combination is therefore not established as unique. To support a claim that it finds an event earlier or finds one those systems miss, preserve alert product versions, observation times and public-availability times, compare matched spatial and temporal coverage, and validate the event independently on a held-out set.

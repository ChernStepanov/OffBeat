# Amazon Sentinel-1 context and C/L comparison (#35)

The prepared [OPERA RTC-S1 series](../data/amazon/sentinel1.json) contains VV and VH gamma0 in dB at the same 1,024 locations as [the NISAR sample](../data/amazon.json), for 86 dates from 2024-01-10 to 2026-11-02. The stored VV and VH arrays contain no nulls; that does not prove all observations are free of noise, geometric effects or other quality problems. The [extraction script](../scripts/opera_rtc.py) reads windows of the RTC GeoTIFFs, samples the nearest 30 m cell and converts positive linear power with 10 log10. Its output records 219 successfully read granules, their dates and CMR IDs. A successful read is not a per-point source receipt: overlapping bursts and versions are filled in first-valid order, and individual contributing granules are not recorded per point.

For example, the stored 2026-09-03 granules include `OPERA_L2_RTC-S1_T170-364106-IW1_20260903T085814Z_20261011T065018Z_S1D_30_v1.0` (other bursts for that date and the complete list are in `provenance.granules`). The acquisition and production dates are different: this is retrospective context, not evidence the product was available on the acquisition date.

## Descriptive class contrast

The script takes the median across available points of each WorldCover 2021 class for each acquisition, then the median of those per-date medians. The C-band dates are all dates within 12 days of any NISAR acquisition: eight dates from 2026-07-17 to 2026-10-09. The L-band comparison uses the six NISAR dates from 2026-07-18 to 2026-09-28. The dates are not paired one-to-one. Class 10 has 575 sample locations and class 30 has 449; WorldCover calls class 30 grassland, not necessarily pasture.

| Class | Sentinel-1 C, VH | NISAR L, HV |
|---|---:|---:|
| Tree cover | −13.79 dB | −12.26 dB |
| Grassland | −14.95 dB | −18.41 dB |
| Tree cover minus grassland | **1.16 dB** | **6.15 dB** |

These are medians of a sparse, spatially dependent sample, not area estimates or an independently validated classification accuracy. WorldCover is historical, and the sensors differ in frequency, acquisition date, incidence geometry, resolution and processing. The contrast does not isolate the effect of wavelength or prove a change in forest cover. A previous issue comment used a tour calculation that selected the upper middle value for even-sized samples; the tour now uses the conventional median, as does the table above. The Python summary rounds the class medians before subtracting them.

## Reproduce from checked-in data

With the project Python dependencies installed, run this from the repository root. This uses the rounded stored RTC measurements and needs no network or Earthdata login:

```sh
.venv/bin/python - <<'PY'
import json
import numpy as np
from scripts.opera_rtc import compare

site = json.load(open('data/amazon.json'))
rtc = json.load(open('data/amazon/sentinel1.json'))
def rows(band):
    return {date: np.array([np.nan if value is None else value for value in row])
            for date, row in zip(rtc['dates'], rtc['points'][band])}
print(json.dumps(compare(site, rtc['dates'], rows('vv'), rows('vh')), indent=2))
PY
```

Re-extraction requires Earthdata access and `python scripts/opera_rtc.py amazon`; its network inputs and resulting data can change. Credentials are not included in the repository.

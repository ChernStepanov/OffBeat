# Science review — 14 November 2026

## Amazon (#19)

On 28 September 2026, the 575 WorldCover tree-cover samples have median NISAR HV
**−12.0055 dB**; the 449 grassland samples have **−15.54589 dB**. Their difference
is **3.54039 dB**. These are sparse-sample medians on a specified date, not forest
area averages. Earlier −12.2 / −18.1 figures must not be reused without their date.
[Every date's counts and medians](../data/analysis/amazon.json),
[original measured values and source receipts](../data/amazon.json).

Scattering within vegetation can change polarization and strengthen HV. NISAR's
L-band interacts with canopy structure differently from shorter wavelengths;
penetration depends on vegetation and moisture. A reduction in HV may be consistent
with clearing or fire, but is not proof of either. WorldCover 2021 class 30 is
grassland, not verified pasture; the contrast is not a biomass estimate.
[NASA NISAR science](https://www.jpl.nasa.gov/press-kits/nisar/mission-overview/science/).

The six downward curve shapes remain unverified. **0 of 6** overlap a forest alert
within ±60 days; **1 of 6** has fire context within 1 km and ±60 days. These are
context matches, not precision, recall or event attribution.
[Dated point validation](../data/amazon/validation.json).

The issue #33 example AMA r5 c15 changes from −9.78809 dB on 23 August to
−17.20815 dB on 4 September (−7.42006 dB), then −17.03645 and −15.86822 dB.
Its latest peer z is −0.41155 and the current classifier gives it no shape.
Own-history change and spatial outlier scores answer different questions.
Its cause remains unknown pending dense geolocated windows, weather/quality checks
and independently interpreted dated optical evidence. No model is trained.

ERA5 reanalysis, accessed retrospectively through Open-Meteo, gives **0.5 mm**
for the seven full UTC days preceding 23 August and **0.4 mm** preceding
4 September. These are coarse 0.25° grid estimates, not point rain-gauge
measurements. The dates exclude the acquisition day to avoid using later hours.
The per-observation original availability date is unverified, so these values
must not be used as historical real-time forecast features without further checks.
No weather correction or causal conclusion is inferred. The request, returned
grid location, daily values and all six date windows are preserved in
[ERA5 evidence](../data/analysis/amazon-era5.json); reproduce with
`python scripts/era5_context.py`. [Open-Meteo ERA5 documentation](https://open-meteo.com/en/docs/historical-weather-api).

## Mexico (#20)

Urban HH can include wall–ground double bounce when viewing geometry is favourable;
HV responds to more complex, depolarizing scattering. Neither is a direct building
height or damage measure. The prepared 12-day GUNW pair has **357/1024** accepted
samples and apparent relative LOS change **−0.87276 to +1.00370 cm**. Reference
sample 743, component 1, was selected by coherence, not proven geological stability.
[Measured values, masks, corrections and reference](../data/mexico.json).

Ionospheric phase is removed; troposphere, tides, unwrapping and reference errors
can remain. We cannot establish whether this pair is dominated by air or ground,
annualize it into subsidence, or infer vertical velocity. Literature reports rates
reaching roughly **50 cm/year in parts of Mexico City**; that is external context,
not our preview's measurement. [Chaussard et al. (2021)](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2020JB020648).

## Venezuela (#21)

The saved current USGS query returns **us6000t7zc, M7.2, 24 June 2026
22:04:31.806 UTC**, at 10.3713°N, 68.5564°W, depth 10 km, and **us6000t7zp,
M7.5, 22:05:04.053 UTC**, at 10.5955°N, 67.2205°W, depth 10 km. Solutions may be
revised; use the retrieval timestamp and exact query rather than mixing preliminary
reports. [Saved USGS records and query](../data/evidence/venezuela-usgs.json),
[USGS M7.5 event](https://earthquake.usgs.gov/earthquakes/eventpage/us6000t7zp/executive).

Our displayed GCOV series ends on 8 January 2026, before the event. A separate
13–25 June GUNW subset has zero samples passing the full unchanged quality mask.
Coherence loss can reflect structural change, moisture, vegetation, geometry or
processing. Comparable pre-event pairs and independent checks are still needed.
No building-damage map or coseismic displacement is demonstrated.
[June GUNW receipt](../data/subsets/venezuela-gunw/2026-06-13_2026-06-25.json).

## L-band, C-band and future use (#22)

NISAR L-band is approximately **24 cm**; Sentinel-1 C-band is about **5.55 cm**.
Longer wavelengths can interact more with woody structure, while canopy penetration,
biomass saturation and moisture sensitivity depend on surface and acquisition
conditions. HH/HV and VV/VH values at different frequencies and geometries cannot
be treated as equivalent measurements. A descriptive comparison for the sampled
Amazon site is documented in [the OPERA RTC analysis](amazon-opera-rtc-comparison.md).
[NASA NISAR facts](https://science.nasa.gov/mission/nisar/mission-overview/),
[ESA Sentinel-1 instrument](https://sentiwiki.copernicus.eu/web/s1-mission).

Longer NISAR histories could support season-aware vegetation monitoring, groundwater
subsidence assessment and flood investigation for land managers and local authorities.
Weather-aware baselines, held-out regions/events and dense, quality-masked windows
with independent checks are planned. They are not demonstrated prediction accuracy
or a current alert service.

## OPERA catalogue checks (#35, #36)

The exact Mexico bbox has catalogue overlap with **1601 dynamic OPERA DISP-S1
granules** and 4 static granules. The Amazon bbox has **653 dynamic OPERA RTC-S1
granules** and 6 static granules. Counts span the collections' available history,
not a processed 2024–2026 series. Query URLs, collection IDs, first 20 returned
granule IDs, dates, footprints and source links are preserved in
[Mexico evidence](../data/evidence/mexico-opera-disp.json) and
[Amazon evidence](../data/evidence/amazon-opera-rtc.json).
Footprint overlap alone does not establish usable pixel coverage or processing compatibility.
Subsequent authenticated RTC-S1 extraction produced a sampled VV/VH series and the
descriptive comparison linked above. No OPERA displacement velocity is claimed; #36 remains open.

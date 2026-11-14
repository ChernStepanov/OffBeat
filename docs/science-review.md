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
Footprint overlap does not establish usable pixel coverage or processing compatibility.
Subsequent authenticated observations are described below.


## Authenticated ASF observations (14 November 2026)

Amazon RTC-S1 is already available as an 86-date series (2024-01-10 through 2026-11-02), with 219 granule identifiers in [the source data](../data/amazon/sentinel1.json). An independently reproducible comparison restricted to the same valid points and six nearest dates within six days gives forest-minus-grassland median contrasts of 1.16 dB for C-band VH and 6.149 dB for L-band HV. The [comparison receipt](../data/analysis/amazon-c-l-matched.json) records matched dates, granules, input hashes and per-class counts. These are descriptive contrasts, not proof of causal mechanisms; sensing geometry, spatial resolutions and times differ, and WorldCover dates from 2021.

For Mexico, 15 OPERA DISP-S1 F01088 products sharing the 2025-12-25 reference were sampled at the NISAR points from 2025-12-31 through 2026-03-25. The [receipt and values](../data/mexico/opera-disp.json) preserve source IDs, dates and processing; each product retains 1018–1021 of 1024 samples under its recommended quality mask. The interface shows short-wavelength relative LOS in cm as independent Sentinel-1 context. Spatial filtering removes wavelengths above 30 km. Atmospheric residuals, component changes and reference stability remain unassessed; this is not vertical displacement or a validated subsidence velocity. See the [ASF DISP FAQ](https://docs.asf.alaska.edu/datasets/disp_faq/) for the product's reference and filtering.

Three Caracas baseline GUNW pairs (2026-05-08→05-20, 05-20→06-01, and 06-01→06-13) were sampled with the unchanged mask. As with the 06-13→06-25 event pair, none of 1024 samples in each pair met the ionospheric uncertainty <=1 rad condition, hence the full mask accepted zero. The [subset receipts](../data/subsets/venezuela-gunw/) retain IDs, hashes and individual quality counts. No damage proxy or coseismic deformation estimate follows from these samples.

For the Amazon candidate AMA r5 c15, two matching native GCOV windows (2026-08-23 and 2026-09-04, 20 m, 141×141 cells) are retained with masks and source hashes in [the subset directory](../data/subsets/amazon-dense/). The [exploratory receipt](../data/analysis/amazon-dense-pair.json) reports the nearest-cell HV change of −7.420 dB and the median of the nine valid 3×3 native cells of −4.122 dB. This is a two-date radar observation, not confirmation of deforestation or a defensible area estimate; moisture, speckle and processing effects are not ruled out.

Six same-track Amazon GCOV windows (2026-07-18 to 2026-09-28) are available on their native 20 m grid with a nearest-neighbour ESA WorldCover 2021 grid and hashes. A [dense peer-z receipt](../data/amazon/dense-peer-z.json) documents all granules and the calculation. Each date has 1,681 valid interior pixels whose full 1 km neighbourhood is inside the extracted window. The optional map layer displays only 2026-09-28, using nearest-neighbour geographic rendering; the acquisition slider does not change it. Missing edges are transparent. These z values describe contemporaneous deviations from neighbours, not confirmed events or temporal change; 2021 land classes can be stale.

### Mexico GUNW pair quality

Three consecutive GUNW pairs were sampled at the existing Mexico points in each of ascending track 019/frame 011 and descending track 113/frame 079. The [quality receipt](../data/analysis/mexico-gunw-quality.json) records source IDs, dates, mask component counts, subset hashes and reproducible processing. Under the unchanged strict mask, accepted counts are 357, 208 and 0 of 1,024 ascending, and 54, 210 and 0 descending; no point passes all three pairs in either sequence. In the third ascending pair, bit 9 of the product mask is set in all sampled cells and the existing anomaly filter excludes them. In the third descending pair, no sampled cell meets the ionospheric-uncertainty threshold. The diagnosis concerns only these short initial sequences, not all available data. A different mask or later disconnected segment needs separate justification; no stable reference, atmospheric correction, rate, or vertical/east decomposition is established here.

Additional Mexico GUNW pairs after the initial gap show that the quality failure is not universal. Four consecutive ascending pairs from 2025-12-17 to 2026-02-03 have 275 of 1,024 points passing all four masks; three descending pairs from 2026-01-05 to 2026-02-10 have 68 points passing all three. Thirty-nine sample coordinates pass both sets of masks. Within each direction, the common points also lie in the dominant independently labelled connected component in every selected pair. The [post-gap quality receipt](../data/analysis/mexico-gunw-postgap-quality.json) preserves granule IDs, dates, quality checks and hashes. This is a necessary quality and connectivity check only: the time intervals differ and the independent stability of a spatial reference, atmospheric residuals, look vectors and uncertainty remain unassessed. No velocity or vertical/east motion is inferred.

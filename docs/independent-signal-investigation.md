# Independent signals: a falsifiable investigation

This is an exploratory follow-up, not a claim of discovery, priority over NASA,
operational capability, or a validated deformation map.

## Candidate: Mexico GNSS and OPERA

The saved Nevada Geodetic Laboratory MMX1 daily GNSS solutions and the nearby
OPERA DISP-S1 sample differ substantially over the common 2025-12-25 to
2026-02-10 window. A linear fit to 48 daily GNSS positions gives vertical
-28.9 cm/year; eight OPERA epochs including the reference give -4.8 cm/year
along the radar line of sight. The nearest radar sample is 20.56 m away. The
formal fit standard errors are 1.0 and 4.5 cm/year respectively, not full
uncertainty estimates; the time window is short and residuals may be correlated.
The quantities use different reference frames and geometry. Their difference is
not evidence that OPERA failed or that its reference point is subsiding.

The existing anchoring experiment shifts the relative OPERA rate field to agree
with projected GNSS at one neighbourhood. Retrospectively varying the anchor
radius from 100, 200, 400 to 800 m gives 5, 18, 69 and 217 sampled locations;
their median raw OPERA anchor rates are -2.51, -2.57, -2.49 and -1.48 cm/year.
The output changes little over the first three radii and by about 1 cm/year at
800 m. This is only local sensitivity to radius: it does not establish accuracy.
The same station is used for anchoring, so agreement there is imposed, not
independent validation. The radar and GNSS fitting windows differ; the code uses
an assumed incidence range and projects only the vertical station component.

Reproduce, from the project root with SciPy installed:

```sh
python -m scripts.experiment_reference_sensitivity
```

The [saved receipt](../data/analysis/mexico-reference-sensitivity.json) contains
input hashes, explicit assumptions and the full radius comparison. Inputs are
[OPERA granule receipt](../data/mexico/opera-disp.json), [GNSS record and source](../data/analysis/mexico-mmx1-gnss.json),
and [measured site samples](../data/mexico.json). ASF documents the distinction
between [unfiltered displacement and short-wavelength displacement](https://docs.asf.alaska.edu/datasets/disp_faq/);
the experiment uses the saved `displacement` values, not the short-wavelength
layer. See also [JPL OPERA DISP specifications](https://www.jpl.nasa.gov/go/opera/products/disp-product-suite/).

## What would test this idea

1. Retrieve exact radar look vectors and a longer GNSS window covering every OPERA date;
   project all available GNSS components and quantify time-correlated errors.
2. Reserve separate GNSS stations or independent survey observations for evaluation;
   anchor only with other stations and repeat leave-one-station-out testing.
3. Compare against a documented baseline and report residuals, uncertainty and
   failures, including sensitivity to reference selection and atmospheric effects.
4. Check multi-event spatially separated regions before claiming generality.

NASA and others already combine radar and GNSS. The potentially useful contribution
here would be a transparent, locally tested workflow that shows disagreement and
its uncertainty. Novelty over existing work has not been established.

## Alternative: L-band/C-band disagreement in Amazonia

The existing [matched C/L receipt](../data/analysis/amazon-c-l-matched.json)
compares six date pairs and the same valid points. Forest-minus-grassland median
contrasts are 6.149 dB for NISAR HV and 1.16 dB for OPERA RTC-S1 VH. These are
descriptive contrasts, not event detection or proof of a wavelength-specific
cause: incidence, date, resolution and historical 2021 cover classes differ.
NASA's [SAR handbook](https://earthdata.nasa.gov/s3fs-public/2025-04/SARHB_CH2_Content.pdf)
documents established SAR change detection; the comparison should be treated as
a candidate for a carefully controlled follow-up, not a new physical discovery.

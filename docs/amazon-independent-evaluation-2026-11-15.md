# Amazon detector: independent evaluation status, 15 November 2026

## Frozen development comparison

The pre-existing `data/benchmark/amazon-v1/protocol.json` fixes the 1,024
samples, K=5/10/20, 20 randomly chosen controls and 2.5 dB threshold before
this comparison, after prior exploration of the area. The entire AOI is one
development group. `python -m scripts.verify_amazon_benchmark` reproduced all
saved rankings: own history 68, comparable-neighbour residual 47, and an
exploratory weather ablation 70 points at the threshold. Every method has
1,024 eligible points. These are flag counts, not verified false positives;
three pre-dates are not enough to validate the weather model.

At each K, all K development candidates have unknown independent labels;
precision bounds are [0,1] and no point estimate is supported. The test split
has zero points, zero positive events and zero labelled negative controls.
Precision@K and false-positive rate are unavailable, not zero. See the frozen
[protocol](../data/benchmark/amazon-v1/protocol.json),
[results](../data/benchmark/amazon-v1/results.json), and
[benchmark description](amazon-benchmark-v1.md).

## Dated material already collected

- `AMA r5 c15`: NISAR 23 August and 4 September 2026; optical views
  [14 August](https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/S2A_22MFV_20260814_0_L2A)
  and [21 September](https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/S2C_22MFV_20260921_0_L2A).
  Signal changes; cause unknown. The optical bracket is wider than the SAR pair.
- `AMA r4 c14`: archived visual review supports clearing between 5 July and
  4 August 2026, but there is insufficient guaranteed pre-event SAR history
  for the fixed detector. This is not a successful test detection.
- `AMA r28 c1`: a retrospective transient-signal comparison, not an independently
  labelled stable control. These three are in the same previously inspected AOI.

See the [casebook](casebook.md), [external audit](amazon-external-audit-v2.md),
[local alert screen](amazon-screening-2026-11-15.md), and checked-in
`data/cases/amazon-v1.json` for sources, dates and limitations.

## Independent material and next step

[MapBiomas Alerta](https://alerta.mapbiomas.org/en/perguntas-frequentes/)
reports that trained analysts verify vegetation loss and bound its timing using
high-resolution before/after imagery. Its [download page](https://plataforma.alerta.mapbiomas.org/downloads)
advertises a public shapefile, while its API documentation requires registration.
The advertised archive URL returned HTTP 404 for an HTTP HEAD request on this
machine; an archive download and its dates/content were not verified. DETER WFS
returned HTTP 502 during the previous wider-area attempt. These failures do not
prove that data do not exist. Do not substitute an alert's publication date for
the actual change interval, nor treat an absence of alerts as a negative label.

Collect independent, dated events and controls in distinct areas, then freeze
candidate IDs, event groups, geography, acquisition windows, K, thresholds and
source hashes **before** inspecting detector rankings. Record independent
before/after evidence, event timing uncertainty, clear/cloud quality and
confirmed/refuted/unknown labels. Hold out whole events, not adjacent samples.
The implementation rejects neighbourhoods from different splits within 2.4 km
(twice the 1.2 km peer radius); event polygons or a larger buffer must still
exclude longer-range event overlap. Report eligible counts and unknown labels;
do not compute precision@K with fewer than K ranked samples.

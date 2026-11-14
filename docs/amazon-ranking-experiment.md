# Amazon change-ranking experiment (issue #33)

Reproduce offline from the repository root:

```bash
/tmp/opencode/nasa-venv/bin/python scripts/experiment_amazon_ranking.py > data/amazon-ranking-experiment.json
/tmp/opencode/nasa-venv/bin/python -m pytest scripts/test_experiment_amazon_ranking.py scripts/test_eda_amazon_sar.py -q
```

The JSON is the captured deterministic output for the checked-in data. The experiment is isolated: it does not modify the existing exploratory script or app/pipeline. It uses the prepared Itupiranga Amazon sample, not Sarov. Event ranking uses **only 2026-08-23 → 2026-09-04**. September 16 and 28 are descriptive follow-up at fixed checkpoint coordinates, never features or inputs to ranking. The checkpoint selection is a fixed code definition, not a claim of preregistration.

## Method and guardrails

HH and HV linear power are converted to dB. Validity uses the same shared HH/HV mask rule as the existing EDA (mask 0/255, non-finite or non-positive power excluded). The ranking population is paired-valid pixels in the target's WorldCover 2021 class 10, with class 0 excluded. WorldCover is a stale class filter, not contemporaneous truth; its transform/CRS is unavailable for independent verification. Data are a sparse clipped sample, not an areal map.

For each eligible pixel, raw change is its after-minus-before dB value. Relative residual is raw change minus the median raw change among paired-valid same-class samples in a centered 3×3, 5×5, or 9×9 window, excluding the pixel itself. At least three local peers are required. Pixels are ordered most-negative residual first. Ties preserve row-major order. Ranks are descriptive sample ranks—not calibrated probabilities or independent-event counts.

## Results

| Polarization | Window | Candidate raw change (dB) | Neighbor median (dB) | Residual (dB) | Rank / eligible class samples |
|---|---:|---:|---:|---:|---:|
| HH | 3×3 | −10.35 | −2.58 | −7.76 | 1 / 543 |
| HH | 5×5 | −10.35 | −2.63 | −7.72 | 1 / 570 |
| HH | 9×9 | −10.35 | −1.39 | −8.96 | 1 / 575 |
| HV | 3×3 | −7.42 | −4.00 | −3.42 | 36 / 543 |
| HV | 5×5 | −7.42 | −2.28 | −5.14 | 5 / 570 |
| HV | 9×9 | −7.42 | −1.11 | −6.31 | 3 / 575 |

The HH and HV rank calculations use the same paired-valid WorldCover-10 sample at each radius (543, 570, and 575 eligible cells respectively). Thus on this common per-radius population the candidate's HV ranks are exactly **36 / 5 / 3** for 3×3 / 5×5 / 9×9. The candidate is first in HH at every radius. Paired local support for the candidate is only 5, 12, and 30 pixels at these radii. This sensitivity and the small/heterogeneous local samples argue against treating rank as a robust anomaly probability.

Five checkpoint coordinates are emitted: candidate r5/c15 and its axial adjacent cells. North (r4/c15) demonstrates why observation validity and class eligibility are separate. It has a valid paired observation under the shared mask, but is WorldCover class 30 rather than target class 10: raw changes are **HH +2.9478 dB** and **HV −2.3930 dB**; paired-neighbor count, neighbor median, and residual are **null** because it is outside the ranked class population. East/south/west are class 10 and their measurements are included in the JSON. The other checkpoints show that the large candidate HH response is not uniform across this tiny neighborhood; neighboring points are spatially dependent samples, **not independent events**.

At candidate r5/c15, follow-up HH on Sep 28 returns near the Aug 23 level, whereas HV remains lower; these later observations are descriptive only and do not retrospectively change the ranking. See the JSON for all checkpoint values and availability.

## Correlations and limitations

No correlation estimate is reported. The series has four acquisition dates, below the existing minimum of n=10; the dates are repeated measurements at one location, not independent events. Treating nearby sampled cells as independent events to inflate correlation sample size would be invalid. In particular, this experiment makes no event-frequency, significance, causal, alert-confirmation, or mapped-area claim.

The experiment checks exact lat/lon array alignment across SAR dates, grid metadata compatibility, SAR signature compatibility, and WorldCover/SAR array shape. WorldCover geotransform/CRS alignment is still unverified. The existing mask bit semantics beyond explicit 0/255 invalid codes remain unverified. Sparse spatial sampling, small neighborhood counts, provisional inputs, and the short acquisition series limit interpretation. The experiment is a reproducible ranking sensitivity check only.

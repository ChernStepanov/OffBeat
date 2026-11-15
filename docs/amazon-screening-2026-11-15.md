# Amazon: reproducibility and local alert screening


`node scripts/test_benchmark_receipts.mjs` verifies the frozen input and report
hashes on Windows as well as Unix. `python -m scripts.verify_amazon_benchmark`
recalculates rankings in memory and compares them to the saved output without
rewriting the original result. All three rankings and threshold counts match.

`node scripts/screen_amazon_alerts.mjs` screens all 575 WorldCover 2021 tree-cover
points against the 65 records in the checked-in alert subset dated after 11 August
through 28 September 2026. It found zero point/polygon matches. The output is
saved in `data/benchmark/amazon-v1/alert-screen.json`, with input SHA-256 hashes.
This is additional retrospective candidate triage within the same development
area, **not** an independent test or a complete source search. Geometry validity
and boundary cases are not resolved by this simple point-in-polygon screen; alert
dates are not event dates, and missing matches are not stable-ground controls.
The TerraBrasilis DETER WFS returned HTTP 502 during a fresh search for events
outside this area; this does not establish whether suitable events exist.

# Mexico: OPERA / NISAR timing audit

The saved [OPERA DISP-S1 subset](../data/mexico/opera-disp.json) has 15
acquisitions from 2025-12-31 to 2026-03-25 with common reference 2025-12-25;
1,018–1,021 of 1,024 sample locations per acquisition have saved values after
the extraction's recommended mask. The audit checks the saved sample counts,
coordinates, finite values, granule identifiers, reference date, ordering and
nearest dates, not the remote mask itself. The per-granule source IDs and URLs
are in the subset; input hashes and offsets are in
[mexico-opera-date-audit.json](../data/analysis/mexico-opera-date-audit.json).

For the later NISAR segments, every descending endpoint is one day before its
nearest saved OPERA observation. Most ascending endpoints are two days before;
the first (2025-12-17) is 14 days before the first OPERA observation. These are
nearest dates only: viewing geometry, reference, processing, filtering and
atmospheric effects differ. This is not a direct displacement agreement or a
validated vertical or LOS speed. NISAR quality intersections remain 275/1024
ascending, 68/1024 descending and 39 common for the respective, differently
dated segments; a stable spatial reference is not established.

Reproduce with `python scripts/audit_mexico_opera_dates.py` and run
`python scripts/test_mexico_opera_dates.py`. For GUNW masks run
`python scripts/test_mexico_gunw_quality.py` and
`python scripts/test_mexico_gunw_postgap.py`.

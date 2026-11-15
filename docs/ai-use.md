# How we used AI tools ("Super Intelligence" disclosure)

Space Apps 2026 allows participants to use LLMs, chatbots, image or video generation, foundation
models and code generation, and asks every submission to say how. This page is that statement for
OffBeat. It is reconstructed from the repository history (231 commits as of 15 November 2026) and
the team's working sessions; where a commit does not record which tool helped, the attribution below
is by area, not commit by commit.

## Tools

| Tool | How it was used |
|---|---|
| **OpenAI Codex** (coding agent) | Implementation, data-processing code, tests, evidence audits and draft documents. Its own commits are authored `Codex` / `CodexSandboxOffline`; team members also worked with it on `codex/...` branches. |
| **Anthropic Claude** (Claude Code, Claude Opus model) | Implementation, design, data analysis code, statistics, documentation and the presentation video, driven from a team member's machine. Its commits are recorded under that team member's git identity. |

No image, video or music generation model was used. No satellite measurement, map value or
statistic was produced by an AI model: every number comes from code run on the measured NASA,
ESA and Copernicus files listed in the README, and synthetic data is rejected by the loader
(`js/data.js`).

## What OpenAI Codex did

- Worldwide NISAR view with optional local overlays, transparent radar tiles, retrying and caching
  NISAR tile requests with an honest "incomplete coverage" report.
- Multilingual place search (GeoNames with Photon fallback, Unicode support).
- Verified sparse-sample analysis, dated Sentinel-2 previews and issue evidence; retrospective ERA5
  precipitation context for Amazon samples.
- Content-hash pinning of JS/CSS so visitors never see a stale mix of files; consistent hashing across
  Windows and deployment line endings.
- Issue audits and status summaries, QA totals, the reviewed slide draft and submission checklist,
  and, with a team member, the reference-sensitivity audit of the GNSS/OPERA comparison.
- Visual audit work on `codex/master-visual-audit`: dated optical evidence centred on the selected
  sample, homepage and help simplifications.

## What Anthropic Claude did

- **Interface:** the Windows 98 look (windows, title bars, bevels, W95FA pixel font, buttons,
  disclosures), Win98 UI sounds, story mode, the landing, a palette test that keeps pale "modern"
  panels out, and later simplification (collapsed layers, 3D terrain on demand, removed clutter).
- **Maps:** NISAR coverage coloured by acquisition date from NASA GIBS (requests only the dates that
  cover a tile, ends on the last fully published day, hides at close zoom), fix for stale tiles of other
  zoom levels showing through, map samples that follow the selected date, playback that animates the
  map through acquisition dates.
- **Data and science code:** Sentinel-1 / NASA OPERA RTC-S1 readers at the NISAR sample points
  (the Earthdata token was handled by a team member only), additional measured NISAR sites, and
  `scripts/findings.py`: join-count permutation tests for spatial clustering, peer-band calibration,
  12-day noise floor, scene-wide shift detection, persistence, Kendall trend tests with
  Benjamini-Hochberg false-discovery control, HH/HV complementarity, physics and coherence checks by
  land cover, a physical plausibility gate (which led the team to remove the Khimki site), and the
  OPERA DISP-S1 versus GNSS MMX1 comparison with a clearly labelled GNSS-anchored estimate.
- **Explanations:** plain-language findings with "How we know" and labelled hypotheses about physical
  drivers ("Why might this happen?"), in English and Russian.
- **Submission material:** the 29.6-second video and its sources (`docs/submission/video/`), the
  Win98-style player on the site, updates to the slides, submission draft, README and QA report.
  The video is built from screenshots of the running app and a chart of measured data, rendered
  frame by frame from HTML; its music is synthesised by a small Python program, and the melody in the
  chart scene is the sonification of a measured sample.

## What people did

- Chose the challenge, the idea of hearing radar "off-beat" pixels, the sites and the overall design.
- Logged in to NASA Earthdata, accepted data-use terms and kept credentials out of every tool.
- Reviewed and steered every change, merged branches, and approved each push to GitHub.
- Made the decisions: removing the implausible Khimki data, the Apache-2.0 licence, wording of claims,
  what goes into the video and the submission.
- Audited AI output: for example, a team member's reference-sensitivity audit (prepared with Codex) showed that an earlier
  AI-written sentence overstated the GNSS/OPERA difference, and the claim was corrected on the site,
  in the video, README and slides.

## Safeguards

- Measured data only; missing values stay missing; no interpolation presented as measurement.
- Automated tests (103 Python, 20 JS scenarios) run before commits; findings are regenerated by
  code and checked against input file hashes.
- Every statistical finding states its strength, its test and its limits; hypotheses about causes
  are labelled as hypotheses.

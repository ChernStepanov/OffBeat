# Mobile, map and music release check

- Browser viewport checks: 320×568, 375×667, 390×844, 430×932, 768×1024 and 844×390. With the 3D panel open, document scroll width equalled the available page width in every check. This is desktop browser responsive testing, not physical iPhone or Safari certification.
- On a narrow screen, the upper maps initially allow page scrolling; “Enable map gestures” enables both maps, and the same button restores scrolling. Desktop map gestures remain enabled. Automated navigation checks cover both modes.
- 3D supports mouse left-drag to move, right-drag to rotate, single-touch move/rotate modes, pinch zoom, and zoom buttons. Physical multi-touch hardware still needs a check.
- Inputs are at least 16 px on phones; header text wraps; safe-area padding accommodates browser/device insets. Zoom remains available.
- “Listen to measured places” offers 17 existing measured samples with at least three valid observations and valid peer spread. Browser QA opened a sample, enabled playback, and stopped it. No new radar measurements are claimed.
- The renamed review flow, visible image filters, corrected Amazon optical dates, visual notes, and HH/HV neighbourhood calculations are included. The seven NASA image comparisons are attributed reference examples.
- Shared reviews pass local API and interface checks. Public write access needs a separately deployed same-origin review service and database; GitHub Pages cannot run it. The UI reports a failed/unavailable service explicitly.
- No tracked project filenames contain “Codex”; no source/provenance files were renamed. Local workspace and tool installation directory names are outside the site's file naming.

Validation: navigation, music selection, sonification, imagery, tile cache, terrain tiles, point-cloud registration, real-data contract, candidate provenance, evidence, visual-audit hashes, NASA comparison hashes, styling, optical dates, multilingual search, API routes and shared-review tests.
